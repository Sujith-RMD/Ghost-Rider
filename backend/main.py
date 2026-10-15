from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks
from pydantic import BaseModel
import json
import os
import uuid

app = FastAPI(title="Ghost-Rider Road Quality API")

ROUTES_DB = {}

class CreateRouteResponse(BaseModel):
    route_id: str
    status: str

@app.get("/")
def read_root():
    return {"message": "Ghost-Rider Road Quality Assessment Backend Running"}

@app.post("/routes", response_model=CreateRouteResponse)
async def create_route():
    route_id = str(uuid.uuid4())
    ROUTES_DB[route_id] = {"images": [], "status": "recording", "results": None}
    os.makedirs(f"uploads/{route_id}", exist_ok=True)
    return {"route_id": route_id, "status": "created"}

@app.post("/routes/{route_id}/images")
async def upload_image(
    route_id: str,
    file: UploadFile = File(...),
    metadata: str = Form(...)
):
    if route_id not in ROUTES_DB:
        return {"error": "Route not found"}
        
    meta_dict = json.loads(metadata)
    file_path = f"uploads/{route_id}/{file.filename}"
    
    with open(file_path, "wb") as f:
        f.write(await file.read())
        
    ROUTES_DB[route_id]["images"].append({
        "image_path": file_path,
        "metadata": meta_dict
    })
    return {"status": "success", "image_id": file.filename}

def run_pipeline_task(route_id: str):
    ROUTES_DB[route_id]["status"] = "completed"
    ROUTES_DB[route_id]["results"] = [
        {
            "segment_id": 1,
            "score": 85,
            "status": "Good",
            "defect_area_m2": 0.05,
            "recommendation": "Road surface intact."
        }
    ]

@app.post("/routes/{route_id}/process")
async def process_route(route_id: str, background_tasks: BackgroundTasks):
    if route_id not in ROUTES_DB:
        return {"error": "Route not found"}
        
    ROUTES_DB[route_id]["status"] = "processing"
    background_tasks.add_task(run_pipeline_task, route_id)
    return {"status": "processing_started", "route_id": route_id}

@app.get("/routes/{route_id}/results")
async def get_results(route_id: str):
    if route_id not in ROUTES_DB:
        return {"error": "Route not found"}
        
    return {
        "route_id": route_id,
        "status": ROUTES_DB[route_id]["status"],
        "segments": ROUTES_DB[route_id]["results"]
    }
