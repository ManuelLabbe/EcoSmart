"""
EcoSmart MCP Server — Lambda handler
Implements MCP protocol (JSON-RPC 2.0) over HTTP for Claude integration.
Exposes sensor readings and alerts from Athena.
"""
import json
import os
import time
import boto3

ATHENA_DB       = "ecosmart_sensors"
ATHENA_WORKGROUP = os.environ.get("ATHENA_WORKGROUP", "ecosmart-workgroup")
S3_OUTPUT       = os.environ.get("S3_OUTPUT", "")

athena = boto3.client("athena", region_name=os.environ.get("AWS_REGION", "us-east-1"))


# ── Athena helpers ────────────────────────────────────────────────────────────

def run_query(sql: str, timeout: int = 25) -> list[dict]:
    resp = athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": ATHENA_DB},
        WorkGroup=ATHENA_WORKGROUP,
    )
    qid = resp["QueryExecutionId"]

    deadline = time.time() + timeout
    while time.time() < deadline:
        status = athena.get_query_execution(QueryExecutionId=qid)
        state  = status["QueryExecution"]["Status"]["State"]
        if state == "SUCCEEDED":
            break
        if state in ("FAILED", "CANCELLED"):
            reason = status["QueryExecution"]["Status"].get("StateChangeReason", "unknown")
            raise RuntimeError(f"Athena query {state}: {reason}")
        time.sleep(1)
    else:
        raise RuntimeError("Athena query timed out")

    pages   = athena.get_paginator("get_query_results").paginate(QueryExecutionId=qid)
    rows    = []
    headers = None
    for page in pages:
        result_rows = page["ResultSet"]["Rows"]
        if headers is None:
            headers = [c["VarCharValue"] for c in result_rows[0]["Data"]]
            result_rows = result_rows[1:]
        for row in result_rows:
            rows.append({
                headers[i]: col.get("VarCharValue", "")
                for i, col in enumerate(row["Data"])
            })
    return rows


# ── MCP Tool implementations ──────────────────────────────────────────────────

def tool_query_sensor_readings(args: dict) -> str:
    limit     = min(int(args.get("limit", 20)), 100)
    equipment = args.get("equipment_id", "")
    node      = args.get("node_id", "")
    filters   = []
    if equipment:
        filters.append(f"equipment_id = '{equipment}'")
    if node:
        filters.append(f"node_id = '{node}'")
    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    sql = f"""
        SELECT reading_id, equipment_id, node_id, node_name,
               air_temp_k, process_temp_k,
               rpm, torque_nm, tool_wear_min,
               anomaly_score, predicted_failure,
               prob_twf, prob_hdf, prob_pwf, prob_osf, prob_rnf
        FROM sensor_readings
        {where}
        ORDER BY reading_id DESC
        LIMIT {limit}
    """
    rows = run_query(sql)
    return json.dumps(rows, indent=2)


def tool_query_alerts(args: dict) -> str:
    limit    = min(int(args.get("limit", 20)), 100)
    severity = args.get("severity", "")
    node     = args.get("node_id", "")
    filters  = []
    if severity:
        filters.append(f"severity = '{severity}'")
    if node:
        filters.append(f"node_id = '{node}'")
    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    sql = f"""
        SELECT equipment_id, node_id, node_name,
               failure_mode, probability, severity,
               anomaly_score, air_temp_k, process_temp_k,
               rpm, torque_nm, tool_wear_min, resolved
        FROM alerts
        {where}
        ORDER BY anomaly_score DESC
        LIMIT {limit}
    """
    rows = run_query(sql)
    return json.dumps(rows, indent=2)


def tool_list_nodes(args: dict) -> str:
    sql = """
        SELECT
            node_id,
            node_name,
            equipment_id,
            COUNT(*)                        AS total_readings,
            ROUND(AVG(anomaly_score), 4)    AS avg_anomaly_score,
            SUM(predicted_failure)          AS total_failures,
            ROUND(MAX(anomaly_score), 4)    AS max_anomaly_score
        FROM sensor_readings
        WHERE node_id <> ''
        GROUP BY node_id, node_name, equipment_id
        ORDER BY avg_anomaly_score DESC
    """
    rows = run_query(sql)
    return json.dumps(rows, indent=2)


def tool_get_equipment_summary(args: dict) -> str:
    sql = """
        SELECT
            equipment_id,
            COUNT(*)                          AS total_readings,
            ROUND(AVG(anomaly_score), 4)      AS avg_anomaly_score,
            SUM(predicted_failure)            AS total_failures,
            ROUND(AVG(prob_pwf), 4)           AS avg_prob_pwf,
            ROUND(AVG(prob_hdf), 4)           AS avg_prob_hdf,
            ROUND(AVG(prob_twf), 4)           AS avg_prob_twf,
            ROUND(AVG(prob_osf), 4)           AS avg_prob_osf,
            ROUND(AVG(prob_rnf), 4)           AS avg_prob_rnf
        FROM sensor_readings
        GROUP BY equipment_id
    """
    rows = run_query(sql)
    return json.dumps(rows, indent=2)


def tool_get_node_trend(args: dict) -> str:
    node    = args.get("node_id", "")
    limit   = min(int(args.get("limit", 50)), 200)
    if not node:
        return json.dumps({"error": "node_id is required"})
    sql = f"""
        SELECT reading_id, node_name,
               ROUND(anomaly_score, 4)     AS anomaly_score,
               predicted_failure,
               ROUND(air_temp_k, 2)        AS air_temp_k,
               ROUND(process_temp_k, 2)    AS process_temp_k,
               rpm,
               ROUND(torque_nm, 2)         AS torque_nm,
               tool_wear_min
        FROM sensor_readings
        WHERE node_id = '{node}'
        ORDER BY reading_id DESC
        LIMIT {limit}
    """
    rows = run_query(sql)
    rows.reverse()  # cronológico ascendente para visualizar tendencia
    return json.dumps(rows, indent=2)


def tool_get_top_risk_equipment(args: dict) -> str:
    limit = min(int(args.get("limit", 5)), 20)
    sql = f"""
        SELECT
            node_id,
            node_name,
            equipment_id,
            COUNT(*)                                                        AS total_readings,
            ROUND(AVG(anomaly_score), 4)                                    AS avg_score,
            ROUND(MAX(anomaly_score), 4)                                    AS max_score,
            SUM(predicted_failure)                                          AS total_failures,
            SUM(CASE WHEN anomaly_score >= 0.65 THEN 1 ELSE 0 END)         AS readings_in_alert,
            ROUND(100.0 * SUM(CASE WHEN anomaly_score >= 0.65 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_in_alert
        FROM sensor_readings
        WHERE node_id <> ''
        GROUP BY node_id, node_name, equipment_id
        ORDER BY avg_score DESC
        LIMIT {limit}
    """
    rows = run_query(sql)
    return json.dumps(rows, indent=2)


def tool_get_failure_mode_heatmap(args: dict) -> str:
    sql = """
        SELECT
            node_name,
            ROUND(AVG(prob_twf), 4) AS prob_twf,
            ROUND(AVG(prob_hdf), 4) AS prob_hdf,
            ROUND(AVG(prob_pwf), 4) AS prob_pwf,
            ROUND(AVG(prob_osf), 4) AS prob_osf,
            ROUND(AVG(prob_rnf), 4) AS prob_rnf,
            ROUND(AVG(anomaly_score), 4) AS avg_anomaly_score,
            CASE
                WHEN AVG(prob_twf) = GREATEST(AVG(prob_twf),AVG(prob_hdf),AVG(prob_pwf),AVG(prob_osf),AVG(prob_rnf)) THEN 'TWF'
                WHEN AVG(prob_hdf) = GREATEST(AVG(prob_twf),AVG(prob_hdf),AVG(prob_pwf),AVG(prob_osf),AVG(prob_rnf)) THEN 'HDF'
                WHEN AVG(prob_pwf) = GREATEST(AVG(prob_twf),AVG(prob_hdf),AVG(prob_pwf),AVG(prob_osf),AVG(prob_rnf)) THEN 'PWF'
                WHEN AVG(prob_osf) = GREATEST(AVG(prob_twf),AVG(prob_hdf),AVG(prob_pwf),AVG(prob_osf),AVG(prob_rnf)) THEN 'OSF'
                ELSE 'RNF'
            END AS dominant_failure_mode
        FROM sensor_readings
        WHERE node_id <> ''
        GROUP BY node_name
        ORDER BY avg_anomaly_score DESC
    """
    rows = run_query(sql)
    return json.dumps(rows, indent=2)


def tool_run_diagnostic(args: dict) -> str:
    node      = args.get("node_id", "")
    equipment = args.get("equipment_id", "")
    if not node and not equipment:
        return json.dumps({"error": "Provide node_id or equipment_id"})

    filter_col = "node_id" if node else "equipment_id"
    filter_val = node or equipment

    stats_sql = f"""
        SELECT
            node_id, node_name, equipment_id,
            COUNT(*)                                                         AS total_readings,
            ROUND(AVG(anomaly_score), 4)                                     AS avg_score,
            ROUND(MAX(anomaly_score), 4)                                     AS max_score,
            SUM(predicted_failure)                                           AS total_failures,
            ROUND(AVG(prob_twf), 4) AS avg_prob_twf,
            ROUND(AVG(prob_hdf), 4) AS avg_prob_hdf,
            ROUND(AVG(prob_pwf), 4) AS avg_prob_pwf,
            ROUND(AVG(prob_osf), 4) AS avg_prob_osf,
            ROUND(AVG(prob_rnf), 4) AS avg_prob_rnf,
            ROUND(AVG(air_temp_k), 2)     AS avg_air_temp_k,
            ROUND(AVG(process_temp_k), 2) AS avg_process_temp_k,
            ROUND(AVG(rpm), 0)            AS avg_rpm,
            ROUND(AVG(torque_nm), 2)      AS avg_torque_nm,
            ROUND(AVG(tool_wear_min), 1)  AS avg_tool_wear_min
        FROM sensor_readings
        WHERE {filter_col} = '{filter_val}'
        GROUP BY node_id, node_name, equipment_id
    """

    recent_sql = f"""
        SELECT ROUND(AVG(anomaly_score), 4) AS recent_avg_score,
               SUM(predicted_failure)       AS recent_failures
        FROM (
            SELECT anomaly_score, predicted_failure
            FROM sensor_readings
            WHERE {filter_col} = '{filter_val}'
            ORDER BY reading_id DESC
            LIMIT 20
        )
    """

    alerts_sql = f"""
        SELECT failure_mode, severity, COUNT(*) AS count,
               ROUND(MAX(anomaly_score), 4) AS max_score
        FROM alerts
        WHERE {filter_col} = '{filter_val}'
        GROUP BY failure_mode, severity
        ORDER BY max_score DESC
        LIMIT 10
    """

    stats   = run_query(stats_sql)
    recent  = run_query(recent_sql)
    alerts  = run_query(alerts_sql)

    probs = {}
    if stats:
        s = stats[0]
        probs = {
            "TWF": float(s.get("avg_prob_twf", 0)),
            "HDF": float(s.get("avg_prob_hdf", 0)),
            "PWF": float(s.get("avg_prob_pwf", 0)),
            "OSF": float(s.get("avg_prob_osf", 0)),
            "RNF": float(s.get("avg_prob_rnf", 0)),
        }
        dominant = max(probs, key=probs.get)
        avg_score = float(s.get("avg_score", 0))
        status = "CRÍTICO" if avg_score >= 0.80 else "ALERTA" if avg_score >= 0.65 else "NORMAL"
    else:
        dominant, status = "N/A", "SIN DATOS"

    diagnostic = {
        "status": status,
        "node_id": filter_val,
        "summary": stats[0] if stats else {},
        "last_20_readings": recent[0] if recent else {},
        "dominant_failure_mode": dominant,
        "failure_mode_probabilities": probs,
        "recent_alerts": alerts,
    }
    return json.dumps(diagnostic, indent=2)


# ── MCP tool registry ─────────────────────────────────────────────────────────

TOOLS = {
    "query_sensor_readings": {
        "description": "Query recent sensor readings from ESP32 devices. Returns air temperature, process temperature, RPM, torque, tool wear and ML failure probabilities. Each reading is tagged with the LoRa node (node_id, node_name) that sourced it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit":        {"type": "integer", "description": "Max rows to return (default 20, max 100)"},
                "equipment_id": {"type": "string",  "description": "Filter by gateway ESP32 ID (e.g. esp32-mach-001). Omit for all."},
                "node_id":      {"type": "string",  "description": "Filter by LoRa node ID (e.g. lora-cal-001). Omit for all nodes."},
            },
        },
        "fn": tool_query_sensor_readings,
    },
    "query_alerts": {
        "description": "Query anomaly alerts generated when the SensorTransformer predicted a failure (anomaly_score >= 0.65). Severity: medium (0.65-0.80), high (0.80-0.90), critical (>0.90). Alerts include the originating LoRa node.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit":    {"type": "integer", "description": "Max rows to return (default 20, max 100)"},
                "severity": {"type": "string",  "description": "Filter by severity: medium, high, or critical. Omit for all."},
                "node_id":  {"type": "string",  "description": "Filter by LoRa node ID. Omit for all nodes."},
            },
        },
        "fn": tool_query_alerts,
    },
    "get_equipment_summary": {
        "description": "Get aggregate stats per equipment: total readings, average anomaly score, failure count and average probability per failure mode (PWF, HDF, TWF, OSF, RNF).",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
        "fn": tool_get_equipment_summary,
    },
    "list_nodes": {
        "description": "List all LoRa sensor nodes aggregated by the ESP32 gateway. Returns node_id, node_name, equipment_id they belong to, total readings, average and max anomaly score, and total failures. Use this to discover available nodes before filtering other tools by node_id.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
        "fn": tool_list_nodes,
    },
    "get_node_trend": {
        "description": "Get the chronological trend of anomaly scores and sensor values for a specific LoRa node. Use this to detect rising patterns before a failure threshold is crossed. Returns readings in ascending time order (oldest first).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_id": {"type": "string",  "description": "LoRa node ID to analyse (e.g. lora-cal-001). Required."},
                "limit":   {"type": "integer", "description": "Number of readings to return (default 50, max 200)."},
            },
            "required": ["node_id"],
        },
        "fn": tool_get_node_trend,
    },
    "get_top_risk_equipment": {
        "description": "Return the N nodes with the highest average anomaly score. Includes % of readings that crossed the alert threshold (0.65). Use this to answer 'what needs attention today?' or 'which equipment is most at risk?'.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "How many top-risk nodes to return (default 5, max 20)."},
            },
        },
        "fn": tool_get_top_risk_equipment,
    },
    "get_failure_mode_heatmap": {
        "description": "Per LoRa node, return the average probability of each failure mode (TWF, HDF, PWF, OSF, RNF) and the dominant failure mode. Use this to understand what type of failure is most likely per equipment and prioritise the right maintenance action.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
        "fn": tool_get_failure_mode_heatmap,
    },
    "run_diagnostic": {
        "description": "Run a full diagnostic for a specific node or equipment. Returns: overall status (NORMAL/ALERTA/CRÍTICO), aggregate sensor stats, failure mode probabilities, dominant failure mode, last-20-reading trend, and recent alert history. Best used when an operator asks for a health report on a specific machine.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "node_id":      {"type": "string", "description": "LoRa node ID (e.g. lora-cal-001). Use this or equipment_id."},
                "equipment_id": {"type": "string", "description": "Gateway ESP32 ID (e.g. esp32-mach-001). Use this or node_id."},
            },
        },
        "fn": tool_run_diagnostic,
    },
}


# ── MCP protocol handlers ─────────────────────────────────────────────────────

def handle_initialize(params: dict, req_id) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "protocolVersion": "2024-11-05",
            "serverInfo": {
                "name":    "ecosmart-mcp",
                "version": "1.0.0",
            },
            "capabilities": {
                "tools": {"listChanged": False},
            },
        },
    }


def handle_tools_list(params: dict, req_id) -> dict:
    tools_list = [
        {
            "name":        name,
            "description": meta["description"],
            "inputSchema": meta["inputSchema"],
        }
        for name, meta in TOOLS.items()
    ]
    return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools_list}}


def handle_tools_call(params: dict, req_id) -> dict:
    name      = params.get("name", "")
    arguments = params.get("arguments", {})

    if name not in TOOLS:
        return {
            "jsonrpc": "2.0", "id": req_id,
            "error": {"code": -32601, "message": f"Tool not found: {name}"},
        }

    try:
        text = TOOLS[name]["fn"](arguments)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"content": [{"type": "text", "text": text}]},
        }
    except Exception as exc:
        return {
            "jsonrpc": "2.0", "id": req_id,
            "error": {"code": -32000, "message": str(exc)},
        }


MCP_METHODS = {
    "initialize":            handle_initialize,
    "tools/list":            handle_tools_list,
    "tools/call":            handle_tools_call,
    "notifications/initialized": lambda p, i: None,
}


# ── Lambda entrypoint ─────────────────────────────────────────────────────────

def lambda_handler(event, context):
    headers = {
        "Content-Type":                "application/json",
        "Access-Control-Allow-Origin": "*",
    }

    if event.get("requestContext", {}).get("http", {}).get("method") == "OPTIONS":
        return {"statusCode": 204, "headers": headers, "body": ""}

    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return {
            "statusCode": 400,
            "headers": headers,
            "body": json.dumps({"error": "Invalid JSON"}),
        }

    method  = body.get("method", "")
    params  = body.get("params", {})
    req_id  = body.get("id")

    handler = MCP_METHODS.get(method)
    if handler is None:
        resp = {
            "jsonrpc": "2.0", "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }
        return {"statusCode": 200, "headers": headers, "body": json.dumps(resp)}

    result = handler(params, req_id)
    if result is None:
        return {"statusCode": 204, "headers": headers, "body": ""}

    return {"statusCode": 200, "headers": headers, "body": json.dumps(result)}
