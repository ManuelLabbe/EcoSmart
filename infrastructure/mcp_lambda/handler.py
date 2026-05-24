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
