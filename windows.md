=========================== short test summary info =========================== 
FAILED tests/test_condition_checker.py::TestAllTasksDone::test_全部完成 - assert False is True
 +  where False = ConditionResult(passed=False, label='\u4efb\u52a1\u5b8c\u6210', detail="'utf-8' codec can't decode byte 0xc8 in position 6: invalid continuation byte").passed
FAILED tests/test_condition_checker.py::TestAllTasksDone::test_无匹配行视为通过 - assert False is True
 +  where False = ConditionResult(passed=False, label='\u4efb\u52a1\u5b8c\u6210', detail="'utf-8' codec can't decode byte 0xc6 in position 10: invalid continuation byte").passed
FAILED tests/test_framework.py::TestFrameworkLoading::test_load_framework_from_json - UnicodeDecodeError: 'utf-8' codec can't decode byte 0xb2 in position 253: invalid start byte
FAILED tests/test_framework.py::TestFrameworkLoading::test_load_multiple_frameworks - UnicodeDecodeError: 'utf-8' codec can't decode byte 0xbf in position 209: invalid start byte
FAILED tests/test_framework_commands.py::TestFrameworkInstall::test_本地框架跳过安装 - UnicodeDecodeError: 'gbk' codec can't decode byte 0xa1 in position 275: illegal multibyte sequence
FAILED tests/test_gate_commands.py::TestGateRespondOwnerOption::test_传owner时命令正常执行 - json.decoder.JSONDecodeError: Extra data: line 9 column 1 (char 131)
FAILED tests/test_gate_request.py::TestGateRequestBlocked::test_blocked_when_prerequisite_not_met - json.decoder.JSONDecodeError: Extra data: line 9 column 1 (char 185)
FAILED tests/test_gate_request.py::TestGateRequestBlocked::test_blocked_result_json_structure - json.decoder.JSONDecodeError: Extra data: line 9 column 1 (char 185)
FAILED tests/test_gate_request.py::TestGateRequestAutoPassFullAuto::test_auto_pass_full_auto_success - json.decoder.JSONDecodeError: Extra data: line 9 column 1 (char 148)
FAILED tests/test_gate_request.py::TestGateRequestAutoPassFullAuto::test_auto_pass_full_auto_next_field - json.decoder.JSONDecodeError: Extra data: line 9 column 1 (char 148)
FAILED tests/test_gate_request.py::TestGateRequestAutoPassNotifyPass::test_auto_pass_notify_pass_output - json.decoder.JSONDecodeError: Extra data: line 9 column 1 (char 148)
FAILED tests/test_gate_request.py::TestGateRequestInteractive::test_condition_failure_triggers_interactive - json.decoder.JSONDecodeError: Extra data: line 9 column 1 (char 138)
FAILED tests/test_gate_request.py::TestGateRequestInteractive::test_interactive_amend_with_note - json.decoder.JSONDecodeError: Extra data: line 9 column 1 (char 143)
FAILED tests/test_gate_request.py::TestGateRequestReworkThreshold::test_rework_threshold_forces_interactive - json.decoder.JSONDecodeError: Extra data: line 13 column 1 (char 294)
FAILED tests/test_load_commands.py::TestLoadCommand::test_输出包含必需字段 - AssertionError: assert 'repos' in {'cli_version': '1.3.8'}
FAILED tests/test_load_commands.py::TestLoadCommand::test_repos始终全量输出 - KeyError: 'repos'
FAILED tests/test_load_commands.py::TestLoadCommand::test_repos字段不含status_version_url - KeyError: 'repos'
FAILED tests/test_load_commands.py::TestTryAutoUpdate::test_更新成功返回system_prompt - assert None is not None
FAILED tests/test_load_commands.py::TestTryAutoUpdate::test_更新成功时system_prompt包含原始命令 - assert None is not None
FAILED tests/test_load_commands.py::TestLoadOpReporter::test_自动更新成功后上报load_auto_updated - assert None is not None
FAILED tests/test_power.py::TestPowerInstallNoArgs::test_remote_power_uninitialized_calls_submodule_update - AssertionError: expected call not found.
Expected: submodule('update', '--init', 'ai-driving/p1')
  Actual: submodule('update', '--init', 'ai-driving\\p1')

pytest introspection follows:

Args:
assert ('update', '--init', 'ai-driving\\p1') == ('update', '--init', 'ai-driving/p1')

  At index 2 diff: 'ai-driving\\p1' != 'ai-driving/p1'

  Full diff:
    (
        'update',
        '--init',
  -     'ai-driving/p1',
  ?                ^
  +     'ai-driving\\p1',
  ?                ^^
    )
FAILED tests/test_power.py::TestEnsurePowerConfigNewBehavior::test_no_checkout_when_no_branch_and_config_exists - TypeError: CliRunner.__init__() got an unexpected keyword argument 'mix_stderr'
FAILED tests/test_power.py::TestEnsurePowerConfigNewBehavior::test_warning_when_no_branch_and_config_missing - TypeError: CliRunner.__init__() got an unexpected keyword argument 'mix_stderr'
FAILED tests/test_repo_commands.py::TestRepoInstall::test_install_no_args_initializes_uninitialized - AssertionError: expected call not found.
Expected: submodule('update', '--init', 'ai-driving/main')
  Actual: submodule('update', '--init', 'ai-driving\\main')

pytest introspection follows:

Args:
assert ('update', '--init', 'ai-driving\\main') == ('update', '--init', 'ai-driving/main')

  At index 2 diff: 'ai-driving\\main' != 'ai-driving/main'

  Full diff:
    (
        'update',
        '--init',
  -     'ai-driving/main',
  ?                ^
  +     'ai-driving\\main',
  ?                ^^
    )
FAILED tests/test_repo_commands.py::TestRepoInstall::test_install_remote_sets_ignore_all - assert 'ignore = all' in '[submodule "ai-driving/myrepo"]\n\tpath = ai-driving/myrepo\n\turl = https://github.com/org/myrepo.git\n'
FAILED tests/test_repo_commands.py::TestRepoInstall::test_install_remote_yet_to_be_born - assert 1 == 0
 +  where 1 = <Result SystemExit(1)>.exit_code
FAILED tests/test_repo_commands.py::TestRepoInstall::test_install_no_args_submodule_add_sets_ignore_all - assert 'ignore = all' in '[submodule "ai-driving/main"]\n\tpath = ai-driving/main\n\turl = https://github.com/org/repo.git\n'
FAILED tests/test_repo_commands.py::TestMigrateLocalToRemote::test_migrate_confirms_and_pushes - OSError: [WinError 1314] 客户端没有所需的特权。: 'C:\\Users\\Administrator\\AppData\\Local\\Temp\\pytest-of-Administrator\\pytest-5\\test_migrate_confirms_and_push0\\my-local' -> 'C:\\Users\\Administrator\\AppData\\Local\\Temp\\pytest-of-Administrator\\pytest-5\\test_migrate_confirms_and_push0\\ai-driving\\my-local'
FAILED tests/test_repo_commands.py::TestMigrateLocalToRemote::test_migrate_skips_push_if_no_git - OSError: [WinError 1314] 客户端没有所需的特权。: 'C:\\Users\\Administrator\\AppData\\Local\\Temp\\pytest-of-Administrator\\pytest-5\\test_migrate_skips_push_if_no_0\\my-local' -> 'C:\\Users\\Administrator\\AppData\\Local\\Temp\\pytest-of-Administrator\\pytest-5_if_no_0\\ai-driving\\my-local'
FAILED tests/test_repo_commands.py::TestRepoUninstall::test_uninstall_lo_if_no_0\\ai-driving\\my-local'
_if_no_0\\ai-driving\\my-local'
FAILED tests/test_repo_commands.py::TestRepoUninstall::test_uninstall_local_symlink - OSError: [WinError 1314] 客户端没有所需的特权。: 'C:\\Users\\Administrator\\AppData\\Local\\Temp\\pytest-of-Administrator\\pytest-5\\test_uninstall_local_symlink0\\src' -> 'C:\\Users\\Administrator\\App_if_no_0\\ai-driving\\my-local'
FAILED tests/test_repo_commands.py::TestRepoUninstall::test_uninstall_local_symlink - OSError: [WinError 1314] 客户端没有所需的特权。: 'C:\\Users\\Administrator\\AppData\\Local\\Temp\\pytest-of-Administrator\\pytest-5\\test_uninstall_local_symlink0\\src' -> 'C:\\Users\\Administrator\\AppData\\Local\\Temp\\pytest-of-Administrator\\pytest-5\\test_uninstall_local_symlink0\\ai-driving\\linked'
========== 30 failed, 1272 passed, 10 skipped, 2 warnings in 18.49s ====_if_no_0\\ai-driving\\my-local'
FAILED tests/test_repo_commands.py::TestRepoUninstall::test_uninstall_local_symlink - OSError: [WinError 1314] 客户端没有所需的特权。: 'C:\\Users\\Administrator\\AppData\\Local\\Temp\\pytest-of-Administrator\\pytest-5\\test_uninstall_local_symlink0\\src' -> 'C:\\Users\\Administrator\\App_if_no_0\\ai-driving\\my-local'
FAILED tests/test_repo_commands.py::TestRepoUninstall::test_uninstall_local_symlink - OSError: [WinError 1314] 客户端没有所需的特权。: 'C:\\User_if_no_0\\ai-driving\\my-local'
_if_no_0\\ai-driving\\my-local'
FAILED tests/test_repo_commands.py::TestRepoUninstall::test_uninstall_local_symlink - OSError: [WinError 1314] 客户端没有所需的特权。: 'C:\\Users\\Administrator\\AppData\\Local\\Temp\\pytest-of-Administrator\\pytest-5\\test_uninstall_local_symlink0\\src' -> 'C:\\Users\\Administrator\\AppData\\Local\\Temp\\pytest-of-Administrator\\pytest-5\\test_uninstall_local_symlink0\\ai-driving\\linked'
========== 30 failed, 1272 passed, 10 skipped, 2 warnings in 18.49s ===========