from datetime import datetime, timezone
import pytest
from agent.informational.models import Context
from agent.informational.relativity import (RelativeVerificationResult, RelativeVerificationStatus, build_informational_frame, derive_frame, is_verification_current)

def context(): return Context(0, "goal", code_hash="a")
def test_frame_is_immutable_and_canonical():
    frame=build_informational_frame(context=context(), observer="sandbox", authority_policy="p1", verification_method="exit_code", evidence_scope=("exit",), criteria=("c",), artifact_versions={"code":"a"})
    assert frame.artifact_versions["code"] == "a"
    with pytest.raises(TypeError): frame.artifact_versions["code"]="b"
def test_artifact_change_derives_reverification_frame():
    frame=build_informational_frame(context=context(), observer="test_runner", authority_policy="p1", verification_method="tests_pass", artifact_versions={"code":"a"})
    derived, transformation=derive_frame(frame, transformation_type="artifact_revision", changed_fields=("artifact_versions",), artifact_versions={"code":"b"})
    assert derived.parent_frame_id == frame.frame_id and transformation.requires_reverification
def test_confidence_does_not_authorize_result():
    now=datetime.now(timezone.utc)
    result=RelativeVerificationResult("v","c","f",RelativeVerificationStatus.UNAUTHORIZED,"reasoning_model","exit_code","unauthorized",(),(),(),(),1.0,now,None,(),"No authority")
    assert result.status is RelativeVerificationStatus.UNAUTHORIZED
def test_relative_result_requires_aware_time():
    with pytest.raises(ValueError): RelativeVerificationResult("v","c","f",RelativeVerificationStatus.SUPPORTED,"sandbox","exit_code","authorized",(),(),(),(),1.0,datetime.now(),None,(),"x")
def test_verification_is_current_only_in_its_frame():
    frame=build_informational_frame(context=context(), observer="sandbox", authority_policy="p", verification_method="exit_code")
    now=datetime.now(timezone.utc); result=RelativeVerificationResult("v","c",frame.frame_id,RelativeVerificationStatus.SUPPORTED,"sandbox","exit_code","authorized",(),(),(),(),1,now,None,(),"x")
    assert is_verification_current(result,frame)
