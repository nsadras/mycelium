"""Opt-in direct probes before enabling selective reasoning in production."""
import asyncio
import json
import time
from pydantic import BaseModel
from benchmarks.probe_support import fresh_run_root
from mycelium import prompts
from mycelium.structured_outputs import extraction_output_model, fact_truth_output_model, fact_synthesis_output_model

ROOT = fresh_run_root("reasoning-policy") / "probes"
SCHEMA_PREFIX = "\n\nReturn one JSON value conforming to this output schema:\n"

async def call(name, system, user, schema, *, think=True, native=False):
    from mycelium.ollama import OllamaClient
    from pydantic import ValidationError
    original_path = ROOT / f"{name}.json"
    validation_path = ROOT / f"{name}-validation.json"
    if validation_path.exists() or original_path.exists():
        raise ValueError(f"Use a fresh probe output directory: {ROOT}")
    print(f"Output: {ROOT}", flush=True)
    shape = schema.model_json_schema()
    base_messages = [{"role":"system","content":system},
        {"role":"user","content":user + SCHEMA_PREFIX + json.dumps(shape, ensure_ascii=False)}]
    request = dict(model="gemma4:12b", messages=base_messages,
        think=think, stream=False, options=dict(temperature=1.0, top_p=0.95, top_k=64,
        seed=17, num_ctx=65536, num_predict=32768))
    if native:
        request["format"] = shape
    ROOT.mkdir(parents=True, exist_ok=True)
    client = OllamaClient("http://localhost:11434", "gemma4:12b", timeout=900)
    outcome = {"attempts": []}
    try:
        for attempt in range(1,4):
            path = original_path if attempt == 1 else ROOT / f"{name}-attempt-{attempt}.json"
            record = {"request":request}
            path.write_text(json.dumps(record,indent=2))
            start = time.monotonic()
            response = await client.client.chat(**request)
            record.update(response=response.model_dump(mode="json",exclude_none=True), seconds=time.monotonic()-start)
            path.write_text(json.dumps(record,indent=2))
            content = record["response"]["message"].get("content", "")
            try:
                result = client._parse_structured_response(content, schema)
                outcome.update(valid=True, result=result)
                outcome["attempts"].append({"path":str(path),"valid":True})
                break
            except (ValidationError, ValueError) as exc:
                outcome["attempts"].append({"path":str(path),"valid":False,"error":str(exc)})
                outcome.update(valid=False,error=str(exc))
                request = {**request,"messages":[*base_messages,
                    {"role":"assistant","content":content},
                    {"role":"user","content":"The response did not satisfy the supplied structured output contract. Correct the response and return the complete JSON value only. Contract error: " + f"{type(exc).__name__}: {exc}"}]}
        validation_path.write_text(json.dumps(outcome,indent=2))
        print(name, outcome, flush=True)
        return outcome
    finally:
        await client.client._client.aclose()

class Record(BaseModel):
    id: str
    text: str

class Records(BaseModel):
    records: list[Record]

async def run_contracts(call):
    records = [{"id":f"S{i}","text":t} for i,t in enumerate([
        "Lena repairs bicycles.", "Lena owns two cats.", "Lena studies geology.",
        "Lena joined a choir in April.", "Lena grows herbs.", "Lena prefers written updates."],1)]
    for think in (False, True):
        await call(f"array-native-{think}", "Return every supplied record as a separate array item, preserving its id and text.",
                   json.dumps(records), Records, think=think, native=True)
    ids=[r["id"] for r in records]
    system,user=prompts.claim_extraction_prompt("agent_conversation","neutral-source",["Lena"],
        "\n\n".join(f"[{r['id']}] speaker=Lena; role=user\n{r['text']}" for r in records))
    for native in (True, False):
        await call(f"extraction-native-{native}",system,user,extraction_output_model(ids),native=native)
    for name,old,new in [
        ("changed", "Lena's bicycle is blue.", "Lena repainted that bicycle green yesterday; it is now green."),
        ("distinct", "Lena's touring bicycle is blue.", "Lena bought a second, green folding bicycle yesterday.")]:
        system,user=prompts.fact_truth_prompt("Lena (person)",
            json.dumps({"C001":{"text":old,"temporal_status":"current"}}),"[]","[]",
            json.dumps({"C002":{"text":new,"temporal_status":"current"}}),"[]")
        await call("truth-"+name,system,user,fact_truth_output_model(["C001"]))
    claims = {f"C{i:03d}":t for i,t in enumerate([
        "Lena attended a workshop on May 3.", "The workshop Lena attended on May 3 began at 9 a.m.",
        "Lena attended a workshop on June 4.", "The workshop Lena attended on June 4 had twelve participants.",
        "Lena is considering learning sailing.", "Lena has not decided whether to learn sailing."],1)}
    system,user=prompts.fact_synthesis_prompt("Lena (person)",json.dumps({a:{"text":t,"temporal_status":"past" if i<4 else "future","temporal":None} for i,(a,t) in enumerate(claims.items())}),
        "[]","[]","history: completed occurrences\nplans: possible future activities")
    await call("synthesis",system,user,fact_synthesis_output_model(claims,["history","plans"]))

if __name__ == "__main__":
    asyncio.run(run_contracts(call))
