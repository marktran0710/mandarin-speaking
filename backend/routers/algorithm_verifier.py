"""Admin Algorithm Verifier API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

import security.auth as auth
from db import connect_db
from services import algorithm_verifier_service as service


router = APIRouter(
    prefix="/api/admin/algorithm-verifier",
    tags=["admin-algorithm-verifier"],
    dependencies=[Depends(auth.require_admin)],
)


@router.get("")
def bootstrap(_identity: auth.Identity = Depends(auth.require_admin)):
    with connect_db() as db:
        try:
            return service.get_bootstrap(db)
        except service.AlgorithmVerifierError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/bkt")
def bkt(payload: dict[str, Any], _identity: auth.Identity = Depends(auth.require_admin)):
    try:
        with connect_db() as db:
            return service.calculate_bkt(payload, db)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/sm2")
def sm2(payload: dict[str, Any], _identity: auth.Identity = Depends(auth.require_admin)):
    try:
        return service.calculate_sm2(payload)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/integration")
def integration(_identity: auth.Identity = Depends(auth.require_admin)):
    with connect_db() as db:
        try:
            return service.get_integration(db)
        except service.AlgorithmVerifierError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/integration/requests")
def integration_requests(_identity: auth.Identity = Depends(auth.require_admin)):
    with connect_db() as db:
        try:
            return service.prepare_integration_requests(db)
        except service.AlgorithmVerifierError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/integration/reset")
def integration_reset(_identity: auth.Identity = Depends(auth.require_admin)):
    with connect_db() as db:
        try:
            return service.reset_integration(db)
        except service.AlgorithmVerifierError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/integration/run")
def integration_run(_identity: auth.Identity = Depends(auth.require_admin)):
    with connect_db() as db:
        try:
            return service.run_integration(db)
        except service.AlgorithmVerifierError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
