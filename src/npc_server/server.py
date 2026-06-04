"""
FastAPI server for serving NPC models for Confident AI evaluation.

This server provides HTTPS endpoints that can be configured as AI Connections
in Confident AI to run evaluations without writing code.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import json
import os
from pathlib import Path

# Add project root to path for imports
import sys
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

app = FastAPI(
    title="Unsloth NPC Server",
    description="Serves NPC models for Confident AI evaluation",
    version="1.0.0"
)


class NPCRequest(BaseModel):
    """Request model for NPC generation."""
    input: str
    context: Optional[List[str]] = []
    hyperparameters: Optional[Dict[str, Any]] = {}
    prompts: Optional[Dict[str, Any]] = None
    conversationalContext: Optional[List[str]] = None
    turns: Optional[List[Dict[str, str]]] = None


class NPCResponse(BaseModel):
    """Response model for NPC generation."""
    output: str
    metadata: Optional[Dict[str, Any]] = {}


class ModelLoader:
    """Loads and manages NPC models."""
    
    def __init__(self):
        self.models = {}
        self.models_dir = project_root / "artifacts" / "models"
    
    def load_model(self, npc_key: str, technique: str = "ollama"):
        """Load a trained NPC model."""
        model_key = f"{npc_key}_{technique}"
        
        if model_key in self.models:
            return self.models[model_key]
        
        # Check if model exists
        model_path = self.models_dir / npc_key / "best"
        if not model_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Model not found for {npc_key} with technique {technique}"
            )
        
        # TODO: Actually load the model using Unsloth/transformers
        # For now, return a mock that simulates model loading
        self.models[model_key] = {
            "path": model_path,
            "npc_key": npc_key,
            "technique": technique
        }
        
        return self.models[model_key]
    
    def generate(self, model_key: str, input_text: str, context: List[str] = None):
        """Generate response using loaded model."""
        if model_key not in self.models:
            raise HTTPException(
                status_code=404,
                detail=f"Model {model_key} not loaded"
            )
        
        model_info = self.models[model_key]
        
        # TODO: Actually generate using the loaded model
        # For now, return a mock response
        mock_response = f"[Mock response from {model_info['npc_key']}]: {input_text}"
        
        return mock_response


model_loader = ModelLoader()


@app.get("/")
async def root():
    """Root endpoint with server info."""
    return {
        "service": "Unsloth NPC Server",
        "version": "1.0.0",
        "endpoints": {
            "/generate": "POST - Generate NPC response",
            "/health": "GET - Health check",
            "/models": "GET - List available models"
        }
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/models")
async def list_models():
    """List available NPC models."""
    models_dir = project_root / "artifacts" / "models"
    
    if not models_dir.exists():
        return {"models": []}
    
    models = []
    for npc_dir in models_dir.iterdir():
        if npc_dir.is_dir():
            models.append({
                "npc_key": npc_dir.name,
                "path": str(npc_dir),
                "has_best": (npc_dir / "best").exists(),
                "has_latest": (npc_dir / "latest").exists()
            })
    
    return {"models": models}


@app.post("/generate", response_model=NPCResponse)
async def npc_generate(request: NPCRequest):
    """
    Generate NPC response.
    
    This endpoint is designed to work with Confident AI AI Connections.
    It accepts the standard payload format and returns the actual output.
    """
    try:
        # Determine which model to use (could be from hyperparameters or default)
        npc_key = request.hyperparameters.get("npc_key", "history_guide")
        technique = request.hyperparameters.get("technique", "ollama")
        
        # Load the model
        model_key = f"{npc_key}_{technique}"
        model_loader.load_model(npc_key, technique)
        
        # Generate response
        context = request.context or []
        if request.conversationalContext:
            context.extend(request.conversationalContext)
        
        output = model_loader.generate(model_key, request.input, context)
        
        return NPCResponse(
            output=output,
            metadata={
                "npc_key": npc_key,
                "technique": technique,
                "model_key": model_key
            }
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Generation failed: {str(e)}"
        )


@app.post("/npc/{npc_key}/generate", response_model=NPCResponse)
async def npc_specific_generate(npc_key: str, request: NPCRequest):
    """Generate response for a specific NPC."""
    try:
        technique = request.hyperparameters.get("technique", "ollama")
        model_key = f"{npc_key}_{technique}"
        
        model_loader.load_model(npc_key, technique)
        
        context = request.context or []
        if request.conversationalContext:
            context.extend(request.conversationalContext)
        
        output = model_loader.generate(model_key, request.input, context)
        
        return NPCResponse(
            output=output,
            metadata={
                "npc_key": npc_key,
                "technique": technique,
                "model_key": model_key
            }
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Generation failed: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    
    # Run the server
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
