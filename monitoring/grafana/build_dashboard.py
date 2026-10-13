"""Build the provisioned Grafana dashboard (dashboards/dc-fabric.json).

    python monitoring/grafana/build_dashboard.py
"""
import json
from pathlib import Path

DS = {"type": "prometheus", "uid": "prometheus"}
OUT = Path(__file__).parent / "dashboards" / "dc-fabric.json"

UPDOWN = [{"type": "value", "options": {
    "0": {"text": "DOWN", "color": "red", "index": 0},
    "1": {"text": "UP", "color": "green", "index": 1}}}]

_next_id = 0


def _id():
    global _next_id
    _next_id += 1
    return _next_id


def target(expr, legend="", instant=False, ref="A"):
    t = {"datasource": DS, "expr": expr, "legendFormat": legend, "refId": ref}
    if instant:
        t.update(instant=True, range=False, format="table")
    return t


def stat(title, expr, x, y, w=4, h=4, thresholds=None, unit="none", desc=""):
    steps = thresholds or [{"color": "green", "value": None}]
    return {
        "id": _id(), "type": "stat", "title": title, "description": desc, "datasource": DS,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "targets": [target(expr)],
        "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "background",
                    "graphMode": "none", "textMode": "value"},
        "fieldConfig": {"defaults": {"unit": unit, "thresholds": {"mode": "absolute", "steps": steps}},
                        "overrides": []},
    }


def timeline(title, expr, legend, x, y, w=12, h=9, desc=""):
    return {
        "id": _id(), "type": "state-timeline", "title": title, "description": desc, "datasource": DS,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "targets": [target(expr, legend)],
        "options": {"showValue": "never", "mergeValues": True, "rowHeight": 0.85,
                    "legend": {"showLegend": False}, "alignValue": "center"},
        "fieldConfig": {"defaults": {"mappings": UPDOWN, "color": {"mode": "thresholds"},
                                     "thresholds": {"mode": "absolute", "steps": [
                                         {"color": "red", "value": None}, {"color": "green", "value": 1}]}},
                        "overrides": []},
    }


def series(title, targets, x, y, w=12, h=9, unit="none", desc="", stack=False):
    return {
        "id": _id(), "type": "timeseries", "title": title, "description": desc, "datasource": DS,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "targets": targets,
        "options": {"legend": {"displayMode": "table", "placement": "right", "calcs": ["lastNotNull", "max"]},
                    "tooltip": {"mode": "multi", "sort": "desc"}},
        "fieldConfig": {"defaults": {"unit": unit, "custom": {
            "lineWidth": 1, "fillOpacity": 10, "showPoints": "never", "spanNulls": False,
            "stacking": {"mode": "normal" if stack else "none"}}}, "overrides": []},
    }


def build():
    p = []
    y = 0
    p.append(stat("Devices polled OK", 'sum(dclab_device_up)', 0, y,
                  thresholds=[{"color": "red", "value": None}, {"color": "green", "value": 5}]))
    p.append(stat("BGP sessions Established", 'sum(dclab_bgp_session_established)', 4, y,
                  thresholds=[{"color": "red", "value": None}, {"color": "green", "value": 12}],
                  desc="Counted from both ends: 6 spine-leaf sessions = 12"))
    p.append(stat("Fabric links down",
                  'count(min by (link) (dclab_interface_oper_up{kind="fabric"}) == 0) or vector(0)', 8, y,
                  thresholds=[{"color": "green", "value": None}, {"color": "red", "value": 1}]))
    p.append(stat("PIM adjacencies", 'sum(dclab_pim_neighbors)', 12, y,
                  thresholds=[{"color": "red", "value": None}, {"color": "green", "value": 12}]))
    p.append(stat("Multicast routes", 'sum(dclab_mroutes)', 16, y))
    p.append(stat("IGMP groups joined", 'sum(dclab_igmp_groups)', 20, y))
    y += 4
    p.append(timeline("Fabric link state (spine-leaf)",
                      'min by (link) (dclab_interface_oper_up{kind="fabric"})', "{{link}}", 0, y,
                      desc="Operational state of each spine-leaf link (DOWN if either end is down)"))
    p.append(timeline("BGP sessions (leaf view)",
                      'dclab_bgp_session_established{device=~"leaf.*"}', "{{device}} -> {{peer_name}}", 12, y))
    y += 9
    p.append(series("Fabric throughput, spine -> leaf (bit/s)", [target(
        'rate(dclab_interface_tx_bytes_total{kind="fabric",device=~"spine.*"}[1m]) * 8',
        "{{device}}:{{interface}} -> {{peer}}")], 0, y, unit="bps"))
    p.append(series("Fabric throughput, leaf -> spine (bit/s)", [target(
        'rate(dclab_interface_tx_bytes_total{kind="fabric",device=~"leaf.*"}[1m]) * 8',
        "{{device}}:{{interface}} -> {{peer}}")], 12, y, unit="bps"))
    y += 9
    p.append(series("Fabric packets/s (rx + tx per link end)", [target(
        'rate(dclab_interface_rx_packets_total{kind="fabric"}[1m]) + '
        'rate(dclab_interface_tx_packets_total{kind="fabric"}[1m])',
        "{{device}}:{{interface}}")], 0, y, unit="pps"))
    p.append(series("Interface errors + drops /s", [target(
        'sum by (device, interface) (rate(dclab_interface_rx_errors_total[1m]) + '
        'rate(dclab_interface_tx_errors_total[1m]) + rate(dclab_interface_rx_dropped_total[1m]) + '
        'rate(dclab_interface_tx_dropped_total[1m]))', "{{device}}:{{interface}}")], 12, y, unit="pps"))
    y += 9
    p.append(series("PIM neighbors per device", [target('dclab_pim_neighbors', "{{device}}")],
                    0, y, w=8, h=8))
    p.append(series("Multicast routes per device", [target('sum by (device) (dclab_mroutes)', "{{device}}")],
                    8, y, w=8, h=8))
    p.append(series("BGP prefixes received", [target(
        'dclab_bgp_prefixes_received', "{{device}} <- {{peer_name}}")], 16, y, w=8, h=8))
    y += 8
    table = {
        "id": _id(), "type": "table", "title": "Link health now", "datasource": DS,
        "gridPos": {"x": 0, "y": y, "w": 24, "h": 10},
        "targets": [target('dclab_interface_oper_up', instant=True)],
        "transformations": [{"id": "organize", "options": {
            "excludeByName": {"Time": True, "__name__": True, "instance": True, "job": True, "lab": True},
            "renameByName": {"Value": "oper"}}}],
        "fieldConfig": {"defaults": {}, "overrides": [{"matcher": {"id": "byName", "options": "oper"},
                                                       "properties": [{"id": "mappings", "value": UPDOWN},
                                                                      {"id": "custom.cellOptions",
                                                                       "value": {"type": "color-background"}}]}]},
        "options": {"sortBy": [{"displayName": "kind", "desc": True}]},
    }
    p.append(table)
    return {
        "uid": "dc-fabric", "title": "DC Fabric - Link Health", "tags": ["dclab", "network"],
        "timezone": "utc", "schemaVersion": 39, "version": 1, "editable": True,
        "refresh": "5s", "time": {"from": "now-15m", "to": "now"},
        "templating": {"list": []}, "annotations": {"list": []}, "panels": p,
    }


if __name__ == "__main__":
    OUT.write_text(json.dumps(build(), indent=2) + "\n")
    print(f"wrote {OUT}")
