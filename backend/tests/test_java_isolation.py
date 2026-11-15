"""Регрессии реальной изоляции и протокола; никакого запуска Java на хосте."""

import os
import subprocess

import pytest

from java_runner import JavaRunnerConfig, JavaCheckStatus, run_java_module
from java_runner.identity import fingerprint_artifact
from java_runner.runner import _parse_state
from model_checker import validate_model
from test_java_runner import JAVA_MACHINE, _artifact


real = pytest.mark.skipif(not os.getenv("JAVA_RUNNER_INTEGRATION"), reason="Нужны Docker и локальный JDK-образ")


@real
@pytest.mark.parametrize("injection", [
    'java.nio.file.Files.readString(java.nio.file.Path.of("/backend/.env"));',
    'new java.net.Socket("1.1.1.1", 53);',
    'byte[] data = new byte[300000000]; System.out.println(data.length);',
])
def test_container_denies_host_files_network_and_heap(buggy_model, tmp_path, injection):
    code = JAVA_MACHINE.replace('System.out.println("READY");', injection + 'System.out.println("READY");')
    result = run_java_module(_artifact(code), buggy_model, JavaRunnerConfig(temp_root=tmp_path))
    assert result.status != JavaCheckStatus.PASSED
    assert list(tmp_path.iterdir()) == []
    names = subprocess.check_output(["docker", "ps", "-a", "--filter", "name=mai-java-", "--format", "{{.Names}}"], text=True)
    assert not names.strip()


@real
def test_rejected_event_cannot_modify_state(buggy_model, tmp_path):
    broken = JAVA_MACHINE.replace('System.out.println("REJECTED");', 'approved = true; System.out.println("REJECTED");')
    result = run_java_module(_artifact(broken), buggy_model, JavaRunnerConfig(temp_root=tmp_path))
    assert result.status == JavaCheckStatus.BEHAVIOR_VIOLATED


@real
def test_limit_is_not_success_and_artifact_identity_preserved(buggy_model, tmp_path):
    artifact = _artifact()
    result = run_java_module(artifact, buggy_model, JavaRunnerConfig(max_checks=1, temp_root=tmp_path))
    assert result.status == JavaCheckStatus.CHECK_LIMIT_REACHED
    assert result.checks_run == 1
    assert result.coverage == "NOT_COMPLETED"
    assert result.compilation == "PASSED"
    assert result.artifact_fingerprint == fingerprint_artifact(artifact)


@pytest.mark.parametrize("path", ["a//Machine.java", "./Machine.java", "a/../Machine.java", "CON:.java", "a/.. /X.java"])
def test_paths_are_canonical_and_portable(path):
    from java_runner import JavaSourceFile
    with pytest.raises(ValueError):
        JavaSourceFile(path=path, content="")


def test_state_parser_supports_enum_delimiters_and_rejects_duplicates():
    model = validate_model({"variables": [{"name": "value", "type": "enum", "values": ['a;b=c', 'a']}],
                            "initial": {"value": "a"},
                            "transitions": [{"name": "Keep", "guard": True, "effects": [{"set": ["value", "a"]}]}],
                            "properties": [{"name": "P1", "type": "invariant", "expression": True}]})
    assert _parse_state('STATE value="a;b=c"', model) == {"value": "a;b=c"}
    assert _parse_state('STATE value=a;value=a', model) is None


@real
@pytest.mark.parametrize("fault", [None, "sequential", "domain"])
def test_integer_enum_operators_and_simultaneous_effects(fault, tmp_path):
    model = {
        "variables": [{"name": name, "type": "integer", "min": 0, "max": 1} for name in ["x", "y"]]
                     + [{"name": "flag", "type": "boolean"}, {"name": "tag", "type": "enum", "values": ["a;b=c"]}],
        "initial": {"x": 0, "y": 1, "flag": False, "tag": "a;b=c"},
        "transitions": [
            {"name": "Swap", "guard": {"and": [{"eq": [{"var": "x"}, 0]}, {"not": {"var": "flag"}}]},
             "effects": [{"set": ["x", {"var": "y"}]}, {"set": ["y", {"var": "x"}]}]},
            {"name": "Reset", "guard": {"or": [{"eq": [{"var": "x"}, 1]}, {"in": [{"var": "tag"}, ["a;b=c"]]}]},
             "effects": [{"set": ["x", 0]}, {"set": ["y", 1]}]},
        ],
        "properties": [{"id": "P1", "type": "invariant", "expression": True}],
    }
    code = r'''
import java.io.*;
public class Machine {
 static int x=0,y=1; static boolean flag=false; static String tag="a;b=c";
 static void state(){System.out.println("STATE x="+x+";y="+y+";flag="+flag+";tag=\""+tag+"\"");}
 public static void main(String[] a) throws Exception {
  System.out.println("READY"); BufferedReader reader=new BufferedReader(new InputStreamReader(System.in));
  String line;
  while((line=reader.readLine())!=null){
   if(line.equals("SNAPSHOT")){state();}
   else if(line.equals("FIRE Swap") && x==0 && !flag){int old=x; x=y; y=old; System.out.println("APPLIED"); state();}
   else if(line.equals("FIRE Reset") && (x==1 || tag.equals("a;b=c"))){x=0;y=1;System.out.println("APPLIED");state();}
   else {System.out.println("REJECTED");}
  }
 }
}
'''
    if fault == "sequential":
        code = code.replace("y=old", "y=x")
    if fault == "domain":
        code = code.replace("x=y", "x=2")
    result = run_java_module(_artifact(code), model, JavaRunnerConfig(temp_root=tmp_path))
    assert result.status == (JavaCheckStatus.PASSED if fault is None else JavaCheckStatus.BEHAVIOR_VIOLATED), result
    if fault is None:
        assert result.checks_run == 6
