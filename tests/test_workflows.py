"""Hand-checked Phase 3 arithmetic, historical gates and publication integration."""

import csv
import json
import socket
from copy import deepcopy
from datetime import date
from decimal import Decimal
from importlib.resources import files

import pytest
from openpyxl import load_workbook

from investment_workspace import pipeline, storage
from investment_workspace.adapters import HISTORY_COLUMNS, inspect_datastore, read_history_csv
from investment_workspace.cli import main
from investment_workspace.schemas import Bundle, Membership, TimingPolicy
from investment_workspace.storage import dumps, read_json
from investment_workspace.workflows import records
from investment_workspace.timing import adjusted_bars, backtest, correlation, rank_rows, reversion


@pytest.fixture
def integrated():
    return json.loads(files("investment_workspace").joinpath("fixtures/phase3-demo.json").read_bytes())


def run(repo, bundle):
    result = pipeline.run(repo, dumps(bundle), workflow="daily")
    return result, read_json(repo, pipeline.STATE)


def row_for(state, collection, ticker="DEMO-BANK"):
    return next(r for r in state["integration"][collection] if r["ticker"] == ticker)


def new_source(bundle, sid):
    source = deepcopy(bundle["sources"][-1])
    source["source_id"] = sid
    bundle["sources"].append(source)
    return sid


def test_timing_split_adjustment_rank_momentum_and_workbook(repo, integrated):
    result, state = run(repo, integrated)
    assert result["status"] == "PARTIAL"
    bank = row_for(state, "timing")
    assert bank["stage"] == "STAGE_2"
    expected = (Decimal(125)/111)/(Decimal(104)/102)-1
    previous = (Decimal(118)/106)/(Decimal(103)/101)-1
    assert abs(Decimal(bank["relative_performance"])-expected) < Decimal("1e-25")
    assert abs(Decimal(bank["rs_momentum"])-(expected-previous)) < Decimal("1e-25")
    assert Decimal(bank["rs_percentile"]) == 100
    assert row_for(state, "timing", "DEMO-LOSS")["stage"] == "STAGE_4"
    history = Bundle.model_validate(integrated).integration.histories[2]
    adjusted = adjusted_bars(history, date(2026,10,9))
    assert adjusted[-2]["close"] == 102
    assert adjusted[-1]["close"] == 105
    assert adjusted[-2]["volume"] == 20000
    assert adjusted[-2]["traded_value"] == Decimal("20000000")
    assert state["integration"]["summary"]["eligible_timing_count"] == 4
    assert state["integration"]["summary"]["schedules_active"] is False
    assert pipeline.validate(repo)["workbook_parity"] == "PASS"
    assert storage.committed(repo, "feeds/latest/timing.json")


def test_rank_ties_are_midrank_and_small_universe_unknown():
    rows = [{"status":"ELIGIBLE", "relative_performance": Decimal(v)} for v in ["0.1","0.1","0"]]
    rank_rows(rows, 2)
    assert [r["rs_percentile"] for r in rows] == [75,75,0]
    rank_rows(rows, 4)
    assert all(r["rs_percentile"] is None for r in rows)


@pytest.mark.parametrize("fault", ["missing_session", "unverified_action", "illiquid", "unverified_calendar", "price_conflict", "stale_actions", "no_benchmark"])
def test_history_gates_do_not_invent_scores(repo, integrated, fault):
    d = integrated["integration"]
    if fault == "missing_session":
        d["histories"][0]["bars"].pop(3)
    elif fault == "unverified_action":
        integrated["sources"][-5]["evidence_label"] = "UNVERIFIED"
    elif fault == "illiquid":
        for b in d["histories"][0]["bars"]:
            b["traded_value"] = "10"
    elif fault == "unverified_calendar":
        d["calendar"]["valid_until"] = "2026-10-08"
        d["calendar"]["effective_date"] = "2026-10-08"
        d["calendar"]["sessions"].pop()
    elif fault == "price_conflict":
        d["histories"][0]["bars"][-1].update(close="126", high="127")
    elif fault == "stale_actions":
        d["histories"][0]["action_coverage_through"] = "2026-10-08"
    else:
        d["histories"].pop()
    result, state = run(repo, integrated)
    assert result["status"] == "PARTIAL"
    bank = row_for(state,"timing")
    assert bank["status"] == "BLOCKED"
    assert bank["rs_percentile"] is None
    assert "relative_performance" not in bank
    assert row_for(state,"watchlist")["stage"] != "READY"


def test_risk_caps_limits_and_scenarios(repo, integrated):
    _, state = run(repo, integrated)
    watch = row_for(state, "watchlist")
    # Assets = 35,670; budget 356.70 / (125-95) = 11.89 whole additional shares.
    assert watch["sizing"]["quantity_cap"] == "11"
    assert watch["sizing"]["status"] == "ILLUSTRATIVE_ONLY"
    assert state["summary"]["sizing_status"] == "BLOCKED"
    assert watch["candidate_type"] == "ADD_ON"
    assert row_for(state, "ic_actions")["action"] == "REVIEW"  # desired 110, price 125
    scenarios = [r for r in state["integration"]["risk"] if r["row_kind"] == "SCENARIO"]
    assert all(Decimal(r["scenario_assets"]) == 38620 for r in scenarios)
    assert abs(Decimal(scenarios[0]["total_return"]) - Decimal(2950)/35670) < Decimal("1e-25")
    assert len(state["integration"]["correlations"]) == 6


@pytest.mark.parametrize("fault", ["unconfirmed", "breach", "stale_holdings", "missing_factor", "no_target", "no_stop_history"])
def test_risk_and_watchlist_blockers(repo, integrated, fault):
    d = integrated["integration"]
    if fault == "unconfirmed":
        d["risk_limits"]["user_confirmed"] = False
    elif fault == "breach":
        d["risk_limits"]["max_position_weight"] = "0.1"
    elif fault == "stale_holdings":
        integrated.setdefault("policy", {})["holdings_max_age_days"] = 0
        integrated["market_cutoff"] = "2026-10-10"
    elif fault == "missing_factor":
        d["factors"].pop(0)
    elif fault == "no_target":
        d["candidates"][0]["requested_target_weight"] = None
    else:
        d["candidates"][0]["stop_price"] = "124"
        # Valid below desired entry must also be below current price; use missing history gate.
        d["candidates"][0]["desired_entry"] = "126"
        d["histories"].pop(0)
    result, state = run(repo, integrated)
    assert result["status"] == "PARTIAL"
    assert row_for(state,"watchlist")["stage"] != "READY"
    assert row_for(state,"ic_actions")["action"] == "REVIEW"


def test_screening_cannot_create_ready_and_thesis_survives(repo, integrated):
    integrated["integration"]["candidates"][0]["requested_stage"] = "RESEARCH"
    _, state = run(repo, integrated)
    watch = row_for(state,"watchlist")
    assert all(watch["gates"].values())
    assert watch["stage"] == "RESEARCH"
    assert watch["thesis"] == integrated["integration"]["candidates"][0]["thesis"]
    assert row_for(state,"ic_actions")["execution_status"] == "NOT_EXECUTED"


def test_event_invalidates_dependents_without_changing_owned_eps(repo, integrated):
    first, before = run(repo, integrated)
    original_earnings = deepcopy(before["research"]["earnings"])
    sid = new_source(integrated,"synthetic.event.1")
    event = {"record_id":"event.oil.1","ticker":"MACRO", "effective_date":"2026-10-09", "valid_until":"2026-10-12", "source_ids":[sid],
             "headline":"Synthetic oil shock", "affected_tickers":["DEMO-ENERGY"], "transmission":"Explicit synthetic volume and margin channel",
             "urgency":"IMMEDIATE", "requires_model_revision":True, "eps_delta":"-2", "eps_period":"FY27", "eps_calculation":"Synthetic supplied volume x unit-margin bridge"}
    integrated["integration"]["events"].append(event)
    second, after = run(repo, integrated)
    assert second["status"] == "PARTIAL"
    assert after["research"]["earnings"] == original_earnings
    assert not any(r["ticker"] == "DEMO-ENERGY" for r in after["research"]["valuations"])
    assert row_for(after,"timing") == row_for(before,"timing")
    assert row_for(after,"propagation","DEMO-ENERGY")["forward_eps_mutated"] is False
    assert row_for(after,"propagation","DEMO-ENERGY")["status"] == "BLOCKED_REVISION"
    # The valuation owner explicitly revises and acknowledges the event; no event module rewrite.
    model = integrated["research"]["models"][1]
    prior_id = model["record_id"]
    model.update(record_id="energy.model.2", supersedes=prior_id, covered_event_ids=[event["record_id"]],
                 source_ids=[new_source(integrated,"synthetic.model.revision.2")])
    for s in model["scenarios"]:
        s["forward_eps"] = "10"
    third, final = run(repo, integrated)
    assert third["status"] == "PARTIAL"
    assert any(r["ticker"] == "DEMO-ENERGY" and r["forward_eps"] == "10" for r in final["research"]["valuations"])
    assert row_for(final,"propagation","DEMO-ENERGY")["status"] == "REUSED_OWNED_INPUTS"


def test_unchanged_rerun_replay_no_network(repo, integrated, tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("offline workflow attempted network")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    first, initial = run(repo, integrated)
    second, after = run(repo, integrated)
    assert second["status"] == "NO_MATERIAL_CHANGE"
    assert initial["integration"] == after["integration"]
    assert after["analysis_run_id"] == first["run_id"]
    target = tmp_path/"phase3.xlsx"
    assert pipeline.replay(repo, first["run_id"], target)["workbook_parity"] == "PASS"


def test_immutable_revisions_and_failure_keep_last_good(repo, integrated):
    _, before = run(repo, integrated)
    integrated["integration"]["candidates"][0]["thesis"] = "silent rewrite"
    result, after = run(repo, integrated)
    assert result["status"] == "FAILED"
    assert before["integration"] == after["integration"]
    assert before["research"] == after["research"]
    assert after["run_log"][-1]["status"] == "FAILED"


def test_signed_correlation_and_constant_variance():
    x = [Decimal(v) for v in [1,2,3,4]]
    assert correlation(x,x,4) == 1
    assert correlation(x,[-v for v in x],4) == -1
    assert correlation(x,[Decimal(1)]*4,4) is None
    assert correlation(x,x,5) is None
    assert reversion([Decimal(10)]*3,3) is None


def test_backtest_next_open_fees_and_point_in_time(integrated):
    policy = deepcopy(integrated["integration"]["timing_policy"])
    policy.update(calibration_status="VALIDATED",backtest_start="2026-10-01",backtest_cost_rate="0.01")
    p = TimingPolicy.model_validate(policy)
    member = Membership.model_validate(integrated["integration"]["memberships"][0])
    days = [date(2026,10,d) for d in [1,2,5,6,7,8]]
    bars = [{"session_date":d,"open":Decimal(o),"close":Decimal(c)} for d,o,c in zip(days,[10,10,8,9,10,12],[10,10,8,9,11,10])]
    result = backtest(bars,p,[member],"DEMO-BANK")
    assert result["status"] == "SIMULATED"
    assert result["closed_trade_count"] == 1
    trade = result["trades"][0]
    assert trade["entry_date"] == "2026-10-06"
    assert trade["entry_price"] == 9
    assert trade["exit_date"] == "2026-10-07"
    assert trade["exit_price"] == 10
    assert abs(trade["return"]-(Decimal("9.9")/Decimal("9.09")-1)) < Decimal("1e-25")
    policy["effective_date"] = "2026-10-02"
    assert backtest(bars,TimingPolicy.model_validate(policy),[member],"DEMO-BANK")["status"] == "BLOCKED"
    policy["effective_date"] = "2026-09-01"
    assert backtest(bars,TimingPolicy.model_validate(policy),[],"DEMO-BANK")["status"] == "BLOCKED"


def test_alerts_strict_threshold_and_missing_methodology(repo, integrated):
    _, before = run(repo, integrated)
    assert before["integration"]["alerts"][0]["bull_triggered"] is None
    a = integrated["integration"]["alert_methodology"]
    a.update(record_id="alerts.2",supersedes="alerts.1", source_ids=[new_source(integrated,"synthetic.alerts.2")],
             approved_replacement=True,methodology_id="explicit-synthetic-replacement",bull_score="8.0",bear_score="8.1")
    _, after = run(repo, integrated)
    alert = after["integration"]["alerts"][0]
    assert alert["bull_triggered"] is False
    assert alert["bear_triggered"] is True
    assert alert["scheduled"] is False


def test_locked_workbook_recovery_carries_phase3_request(repo, integrated, monkeypatch):
    original = storage.atomic_write
    def locked(path,data):
        if path == repo/pipeline.WORKBOOK:
            raise PermissionError("workbook locked")
        return original(path,data)
    monkeypatch.setattr(storage,"atomic_write",locked)
    with pytest.raises(storage.PublicationError):
        run(repo,integrated)
    monkeypatch.setattr(storage,"atomic_write",original)
    pipeline.recover(repo)
    state = read_json(repo,pipeline.STATE)
    assert state["integration"]["summary"]["eligible_timing_count"] == 4
    assert pipeline.validate(repo)["workbook_parity"] == "PASS"


def test_import_adapters_and_datastore_inventory(repo, integrated, tmp_path):
    data = integrated.pop("integration")
    needed = {s for _,r in records(Bundle.model_validate({**integrated,"integration":data}).integration) for s in r.source_ids}
    sources = [s for s in integrated["sources"] if s["source_id"] in needed]
    integrated["sources"] = [s for s in integrated["sources"] if s["source_id"] not in needed]
    run(repo,integrated)
    packet={"sources":sources,"integration":data}
    assert pipeline.import_integration(repo,dumps(packet))["status"] == "PARTIAL"
    path = tmp_path/"bars.csv"
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=HISTORY_COLUMNS)
        writer.writeheader()
        writer.writerows(data['histories'][0]['bars'])
    assert read_history_csv(path) == data['histories'][0]['bars']
    inventory = inspect_datastore(repo/pipeline.WORKBOOK)
    assert inventory['modified'] is False
    assert inventory['compatibility_status'].startswith('INVENTORY_ONLY')
    assert any(s['sheet']=='RS_Trend' for s in inventory['sheets'])


def test_tampered_workbook_timing_is_rejected(repo, integrated, tmp_path):
    from investment_workspace.excel import validate_workbook
    _, state = run(repo,integrated)
    wb=load_workbook(repo/pipeline.WORKBOOK)
    ws=wb['RS_Trend'];headers=[c.value for c in ws[1]]
    ws.cell(2,headers.index('rs_percentile')+1,0)
    path=tmp_path/'tampered.xlsx';wb.save(path);wb.close()
    with pytest.raises(ValueError,match='parity'):
        validate_workbook(path,state)


def test_phase3_cli_init_and_daily_ic(repo,tmp_path):
    assert main(['--root',str(repo),'init','--offline','--phase3']) == 0
    assert main(['--root',str(repo),'run','ic','--offline']) == 0
    assert main(['--root',str(repo),'analyze','DEMO-BANK','--offline']) == 0
    assert main(['--root',str(repo),'validate']) == 0


def test_incomplete_owned_scenarios_block_caps_and_leave_totals_unknown(repo,integrated):
    integrated['research']['models'].pop()
    _, state = run(repo,integrated)
    scenarios=[r for r in state['integration']['risk'] if r['row_kind']=='SCENARIO']
    assert all(r['scenario_assets'] is None for r in scenarios)
    assert row_for(state,'watchlist')['sizing']['quantity_cap'] is None
    assert row_for(state,'watchlist')['stage'] != 'READY'


def test_candidate_revision_preserves_user_history(repo,integrated):
    _, initial=run(repo,integrated)
    candidate=integrated['integration']['candidates'][0]
    old_id=candidate['record_id']
    candidate.update(record_id='candidate.bank.2',supersedes=old_id,
                     source_ids=[new_source(integrated,'synthetic.candidate.2')],thesis='User-authored revised thesis')
    _, after=run(repo,integrated)
    assert row_for(after,'watchlist')['thesis']=='User-authored revised thesis'
    history=after['integration']['history']
    old_record=next(r for r in history if r['record_id']==old_id)
    assert old_record['payload']['thesis']==row_for(initial,'watchlist')['thesis']
    assert len(history)==len(initial['integration']['history'])+1


def test_add_requires_confirmed_entry_trigger_not_screen_alone(repo,integrated):
    # A more conservative exit/hurdle fixture makes the explicit entry ceiling >125.
    for s in integrated['research']['models'][0]['scenarios']:
        s['exit_price']='150'
    c=integrated['integration']['candidates'][0]
    c['desired_entry']='125'
    _, state=run(repo,integrated)
    assert row_for(state,'watchlist')['stage']=='READY'
    assert row_for(state,'watchlist')['monitoring_state']=='TRIGGERED'
    assert row_for(state,'ic_actions')['action']=='ACCUMULATE'
    assert row_for(state,'ic_actions')['decision_status']=='PROPOSED'
    assert state['holdings'][0]['quantity']=='80'


def test_new_position_is_distinct_from_addon(repo,integrated):
    c=deepcopy(integrated['integration']['candidates'][0])
    c.update(record_id='candidate.new.1',ticker='DEMO-NEW',requested_stage='PRICE_WATCH',catalyst_ids=[])
    integrated['integration']['candidates'].append(c)
    _,state=run(repo,integrated)
    row=row_for(state,'watchlist','DEMO-NEW')
    assert row['candidate_type']=='NEW_POSITION'
    assert row['stage']!='READY'
    assert any(r['ticker']=='DEMO-NEW' and r['outcome']=='BLOCKED_MODEL' for r in state['coverage'])


def test_event_packet_cli_and_qualitative_no_eps_fabrication(repo,integrated,tmp_path):
    run(repo,integrated)
    source=new_source(integrated,'synthetic.qualitative.event')
    integrated['integration']['events'].append({'record_id':'qualitative.1','ticker':'MACRO','effective_date':'2026-10-09',
       'valid_until':'2026-10-12','source_ids':[source],'headline':'Synthetic external stress','affected_tickers':['DEMO-BANK'],
       'transmission':'Qualitative channel only; magnitude unavailable','urgency':'WATCH','requires_model_revision':False})
    path=tmp_path/'event.json'
    path.write_bytes(dumps({'sources':[integrated['sources'][-1]],'integration':integrated['integration']}))
    assert main(['--root',str(repo),'run','event','--ticker','DEMO-BANK','--source-file',str(path),'--offline'])==0
    s=read_json(repo,pipeline.STATE)
    assert s['integration']['events'][0]['eps_delta'] is None
    assert s['integration']['events'][0]['impact_kind']=='QUALITATIVE'


def test_foreign_source_or_post_cutoff_bar_rejected(repo,integrated):
    _,before=run(repo,integrated)
    integrated['integration']['histories'][0]['bars'][-1]['session_date']='2026-10-10'
    result,after=run(repo,integrated)
    assert result['status']=='FAILED'
    assert after['integration']==before['integration']


def test_manual_model_blocks_cannot_be_overridden_by_automatic_gates(repo, integrated):
    integrated['research']['models'][0]['risk_gate']='BLOCKED'
    _,state=run(repo,integrated)
    assert row_for(state,'watchlist')['stage']!='READY'
    entry=next(r for r in state['research']['entries'] if r['ticker']=='DEMO-BANK')
    assert entry['resolved_risk_gate']=='BLOCKED'
    assert entry['entry_status']=='BLOCKED'


def test_backtest_rejects_post_start_parameter_evidence(repo,integrated):
    integrated['integration']['timing_policy']['calibration_status']='VALIDATED'
    source=next(s for s in integrated['sources'] if s['source_id']=='synthetic.policy.v1')
    source['effective_date']='2026-10-09'
    _,state=run(repo,integrated)
    assert all(r['status']=='BLOCKED' and 'historical decision' in r['reason'] for r in state['integration']['backtests'])


def test_old_placeholder_workbook_remains_valid_for_replay(repo,bundle,tmp_path):
    from investment_workspace.excel import validate_workbook
    pipeline.run(repo,dumps(bundle))
    state=read_json(repo,pipeline.STATE)
    wb=load_workbook(repo/pipeline.WORKBOOK)
    for name in ('RS_Trend','Mean_Reversion','Watchlist','Valuation'):
        ws=wb[name]
        ws.delete_rows(1,ws.max_row)
        ws.append(['status','reason'])
        ws.append(['NOT_IMPLEMENTED','No accepted model or live data migrated; see docs/migration.md'])
    target=tmp_path/'legacy.xlsx';wb.save(target);wb.close()
    validate_workbook(target,state)


def test_csv_adapter_cli_idempotency(repo,integrated,tmp_path):
    run(repo,integrated)
    d=integrated['integration']
    packet=tmp_path/'packet.json'
    packet.write_bytes(dumps({'sources':[],'integration':d}))
    bars=tmp_path/'history.csv'
    with bars.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=HISTORY_COLUMNS);w.writeheader();w.writerows(d['histories'][0]['bars'])
    assert main(['--root',str(repo),'import-history','--file',str(bars),'--packet',str(packet),'--history-id','DEMO-BANK.history.1'])==0
    assert read_json(repo,pipeline.STATE)['attempt_status']=='NO_MATERIAL_CHANGE'


def test_malformed_csv_publishes_failure_and_preserves_analysis(repo,integrated,tmp_path):
    _,before=run(repo,integrated)
    packet=tmp_path/'packet.json';packet.write_bytes(dumps({'sources':[],'integration':integrated['integration']}))
    bars=tmp_path/'bad.csv';bars.write_text('ticker,price\nDEMO-BANK,125\n')
    assert main(['--root',str(repo),'import-history','--file',str(bars),'--packet',str(packet),'--history-id','DEMO-BANK.history.1'])==1
    after=read_json(repo,pipeline.STATE)
    assert after['integration']==before['integration']
    assert after['run_log'][-1]['workflow']=='import-history'
    assert after['run_log'][-1]['status']=='FAILED'


def test_conflicting_price_in_another_holding_blocks_portfolio_sizing(repo,integrated):
    bar=integrated['integration']['histories'][1]['bars'][-1]
    bar.update(close='111',high='112')
    _,state=run(repo,integrated)
    assert row_for(state,'timing')['status']=='ELIGIBLE'
    assert row_for(state,'watchlist')['sizing']['quantity_cap'] is None
    assert row_for(state,'watchlist')['stage']!='READY'


def test_missing_price_does_not_become_partial_sector_or_factor_total(repo,integrated):
    integrated['prices'][2]['close']=None
    _,state=run(repo,integrated)
    sector=next(r for r in state['integration']['risk'] if r['row_kind']=='SECTOR' and r['name']=='Industrial')
    factor=next(r for r in state['integration']['risk'] if r['row_kind']=='FACTOR' and r['name']=='DOMESTIC_CYCLE')
    assert sector['value'] is None
    assert factor['value'] is None
    assert sector['weight_total_sleeve'] is None
    assert state['summary']['total_assets'] is None
