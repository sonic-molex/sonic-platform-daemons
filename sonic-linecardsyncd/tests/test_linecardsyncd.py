#!/usr/bin/env python3
"""
test_linecard_4.py - Linecardsyncd unit test suite
Test strategy:
1.Fully comprehensively cover basic functions and boundary cases
2.Precisely simulate external dependency behaviors
3.Verify all possible error handling paths
4.Ensure correctness and atomicity of database operations
"""

import os
import sys
from imp import load_source
import json
import signal
import pytest
from sonic_py_common import daemon_base
from swsscommon import swsscommon
import unittest.mock as mock

test_path = os.path.dirname(os.path.abspath(__file__))
modules_path = os.path.dirname(test_path)
scripts_path = os.path.join(modules_path, "scripts")
sys.path.insert(0, modules_path)

load_source('linecardsyncd', scripts_path + '/linecardsyncd')
import linecardsyncd
from linecardsyncd import (
    get_chassis,
    CfgManager,
    LineCardManager,
    DaemonLinecardSyncd,
    CHASSIS_LOAD_ERROR,
    SYSLOG_IDENTIFIER,
    LINECARD_INFO_TABLE,
    LINECARD_STATUS_FIELD,
    LINECARD_SLOT_FIELD,
    LINECARD_TYPE_FIELD,
    LINECARD_VERSION_FIELD,
    LINECARD_PARENT_FIELD,
    ModuleBase
)

# =================================================================
# Fixtures
# =================================================================

# Test fixture to mock the platform class
@pytest.fixture
def mock_platform():
    """Mock Platform class to provide basic platform functionality"""
    with mock.patch("sonic_platform.platform.Platform") as mock_platform_cls:
        mock_platform = mock.Mock()
        mock_platform_cls.return_value = mock_platform
        yield mock_platform

# Test fixture to create a mock chassis with line cards and components
@pytest.fixture
def mock_chassis(mock_platform):
    """Create a mock chassis with two line cards and components
    - linecard-1: online with sfp-1 component
    - linecard-2: offline with no components
    """
    chassis = mock.Mock()
    mock_platform.get_chassis.return_value = chassis
    chassis.get_name.return_value = "chassis-1"

    lc1 = mock.Mock()
    lc1.get_name.return_value = "linecard-1"
    lc1.get_slot.return_value = "1"
    lc1.get_type.return_value = "OT-LC"
    lc1.get_oper_status.return_value = ModuleBase.MODULE_STATUS_ONLINE

    lc2 = mock.Mock()
    lc2.get_name.return_value = "linecard-2"
    lc2.get_slot.return_value = "2"
    lc2.get_type.return_value = "OT-LC"
    lc2.get_oper_status.return_value = ModuleBase.MODULE_STATUS_OFFLINE

    comp1 = mock.Mock()
    comp1.get_name.return_value = "sfp-1"
    comp1.get_firmware_version.return_value = "1.0.0"
    comp1.get_oper_status.return_value = ModuleBase.MODULE_STATUS_ONLINE

    lc1.get_all_components.return_value = [comp1]
    lc2.get_all_components.return_value = []

    chassis.get_all_modules.return_value = [lc1, lc2]

    return chassis

@pytest.fixture
def mock_db_connectors():
    with mock.patch.object(daemon_base, "db_connect") as mock_connect:
        mock_app_db = mock.Mock()
        mock_cfg_db = mock.Mock()
        mock_sta_db = mock.Mock()
        mock_connect.side_effect = [mock_app_db, mock_cfg_db, mock_sta_db]
        yield {
            "app_db": mock_app_db,
            "cfg_db": mock_cfg_db,
            "sta_db": mock_sta_db
        }

@pytest.fixture
def mock_platform_path():
    with mock.patch("sonic_py_common.device_info.get_path_to_platform_dir") as mock_path:
        mock_path.return_value = "/tmp/platform"
        yield mock_path

@pytest.fixture
def mock_producer_state_table():
    with mock.patch('swsscommon.swsscommon.ProducerStateTable') as mock_pst:
        mock_instance = mock.Mock()
        mock_instance.set = mock.Mock()
        mock_instance.delete = mock.Mock()
        mock_pst.return_value = mock_instance
        yield mock_pst

@pytest.fixture(autouse=True)
def mock_sonic_platform():
    """Mock sonic_platform module for all tests"""
    mock_platform = mock.MagicMock()
    sys.modules['sonic_platform'] = mock_platform
    sys.modules['sonic_platform.platform'] = mock_platform.platform
    yield mock_platform
    del sys.modules['sonic_platform']
    del sys.modules['sonic_platform.platform']

# =================================================================
# get_chassis tests
# =================================================================

# Test successful chassis initialization and retrieval
@mock.patch("sonic_platform.platform.Platform")
def test_get_chassis_with_valid_platform(mock_platform, mock_chassis):
    """Test get_chassis() successfully retrieves chassis when platform is valid"""
    mock_platform.return_value.get_chassis.return_value = mock_chassis
    result = get_chassis()
    assert result == mock_chassis
    mock_platform.return_value.get_chassis.assert_called_once()


# Test chassis initialization failure handling
@mock.patch("sonic_platform.platform.Platform")
def test_get_chassis_platform_init_failure(mock_platform):
    """Test get_chassis() handles platform initialization failure gracefully"""
    mock_platform.return_value.get_chassis.side_effect = RuntimeError("Hardware error")
    with pytest.raises(SystemExit) as exc_info:
        get_chassis()
    assert exc_info.value.code == CHASSIS_LOAD_ERROR


# =================================================================
# CfgManager tests
# =================================================================

# Test config manager initialization with valid JSON data
@mock.patch("builtins.open", new_callable=mock.mock_open)
@mock.patch("os.path.isfile")
@mock.patch("sonic_py_common.device_info.get_path_to_platform_dir")
def test_cfgmanager_init_with_valid_json(mock_path, mock_isfile, mock_open_):
    """Test CfgManager successfully loads valid JSON configuration file"""
    test_data = {"linecard-1": ["extra1", "extra2"]}
    json_str = json.dumps(test_data)
    mock_path.return_value = "/tmp/platform"
    mock_isfile.return_value = True
    mock_open_.return_value.read.return_value = json_str
    cm = CfgManager(SYSLOG_IDENTIFIER)
    assert cm.json_data == test_data
    mock_open_.assert_called_once_with('/tmp/platform/linecard_extra_map.json', "r")


# Test config manager handling of invalid JSON format
@mock.patch("sonic_py_common.device_info.get_path_to_platform_dir")
@mock.patch("builtins.open", side_effect="invalid json")
def test_cfgmanager_with_invalid_json_format(mock_open_, mock_path):
    """Test CfgManager handles invalid JSON format gracefully"""
    cm = CfgManager(SYSLOG_IDENTIFIER)
    assert cm.json_data is None
    assert cm.get_values("any-key") is None


# Test config manager handling of missing configuration file
@mock.patch("sonic_py_common.device_info.get_path_to_platform_dir")
@mock.patch("builtins.open", side_effect=FileNotFoundError)
def test_cfgmanager_with_missing_file(mock_open_, mock_path):
    """Test CfgManager handles missing configuration file gracefully"""
    cm = CfgManager(SYSLOG_IDENTIFIER)
    assert cm.json_data is None

# =================================================================
# LineCardManager tests
# =================================================================

@pytest.fixture
def linecard_manager(mock_chassis, mock_db_connectors, mock_platform_path):
    with mock.patch.object(swsscommon.SonicDBConfig, "getSeparator", return_value="|"), \
         mock.patch("builtins.open", mock.mock_open(read_data="{}")):
        manager = LineCardManager(SYSLOG_IDENTIFIER, mock_chassis)
        yield manager


# Test line card info update functionality
@mock.patch('swsscommon.swsscommon.ProducerStateTable')
@mock.patch.object(daemon_base, "db_connect")
@mock.patch("sonic_py_common.device_info.get_path_to_platform_dir")
@mock.patch("builtins.open", new_callable=mock.mock_open, read_data="{}")
@mock.patch.object(swsscommon.SonicDBConfig, "getSeparator", return_value="|")
def test_linecard_manager_info_update_success(
    mock_sep, mock_open_, mock_platform_path, mock_connect, mock_prod_state_table, mock_chassis
):
    """Test LineCardManager successfully updates line card status information in state DB"""
    mock_app_db = mock.Mock()
    mock_cfg_db = mock.Mock()
    mock_sta_db = mock.Mock()
    mock_connect.side_effect = [mock_app_db, mock_cfg_db, mock_sta_db]
    mock_instance = mock.Mock()
    mock_prod_state_table.return_value = mock_instance

    manager = LineCardManager(SYSLOG_IDENTIFIER, mock_chassis)
    mock_cfg_db.keys.return_value = []
    mock_app_db.keys.return_value = []
    mock_app_db.exists.return_value = True

    manager.linecard_info_update()

    print("\nAll hset calls:")
    for c in mock_sta_db.hset.call_args_list:
        print(f"hset{c}")

    mock_sta_db.hset.assert_any_call(
        f"{LINECARD_INFO_TABLE}|linecard-1",
        LINECARD_STATUS_FIELD,
        str(ModuleBase.MODULE_STATUS_ONLINE)
    )
    mock_sta_db.hset.assert_any_call(
        f"{LINECARD_INFO_TABLE}|linecard-2",
        LINECARD_STATUS_FIELD,
        str(ModuleBase.MODULE_STATUS_OFFLINE)
    )


# Test line card component handling
@mock.patch('swsscommon.swsscommon.ProducerStateTable')
@mock.patch.object(daemon_base, "db_connect")
@mock.patch("sonic_py_common.device_info.get_path_to_platform_dir")
@mock.patch("builtins.open", new_callable=mock.mock_open, read_data="{}")
@mock.patch.object(swsscommon.SonicDBConfig, "getSeparator", return_value="|")
def test_linecard_manager_component_handling(
    mock_sep, mock_open_, mock_platform_path, mock_connect, mock_prod_state_table, mock_chassis
):
    """Test LineCardManager properly handles component information and versions"""
    mock_app_db = mock.Mock()
    mock_cfg_db = mock.Mock()
    mock_sta_db = mock.Mock()
    mock_connect.side_effect = [mock_app_db, mock_cfg_db, mock_sta_db]
    mock_instance = mock.Mock()
    mock_prod_state_table.return_value = mock_instance

    manager = LineCardManager(SYSLOG_IDENTIFIER, mock_chassis)
    mock_app_db.exists.return_value = True
    mock_app_db.keys.return_value = ["SFP_CONFIG_TABLE|sfp-1"]
    manager.linecard_info_update()
    mock_sta_db.hset.assert_any_call(
        f"{LINECARD_INFO_TABLE}|sfp-1",
        LINECARD_VERSION_FIELD,
        "1.0.0"
    )


# Test restore operations for line card configurations
@mock.patch('swsscommon.swsscommon.ProducerStateTable')
@mock.patch.object(daemon_base, "db_connect")
@mock.patch("sonic_py_common.device_info.get_path_to_platform_dir")
@mock.patch("builtins.open", new_callable=mock.mock_open, read_data="{}")
@mock.patch.object(swsscommon.SonicDBConfig, "getSeparator", return_value="|")
def test_linecard_manager_restore_operations(
    mock_sep, mock_open_, mock_platform_path, mock_connect, mock_prod_state_table, mock_chassis
):
    """Test LineCardManager correctly restores line card configurations from config DB to app DB"""
    mock_app_db = mock.Mock()
    mock_cfg_db = mock.Mock()
    mock_sta_db = mock.Mock()
    mock_connect.side_effect = [mock_app_db, mock_cfg_db, mock_sta_db]
    mock_instance = mock.Mock()
    mock_prod_state_table.return_value = mock_instance

    manager = LineCardManager(SYSLOG_IDENTIFIER, mock_chassis)
    mock_cfg_db.keys.side_effect = [[], ["SFP_CONFIG_TABLE|sfp-1"]]
    mock_cfg_db.hgetall.return_value = {"speed": "25G"}
    mock_app_db.exists.return_value = False

    manager._restore_app_table("sfp-1")
    mock_prod_state_table.assert_called_once_with(mock_app_db, "SFP_CONFIG_TABLE_TABLE")
    mock_instance.set.assert_called_once_with("sfp-1", [("speed", "25G")])


# Test all restore operation scenarios
@mock.patch.object(swsscommon.SonicDBConfig, "getSeparator", return_value="|")
@mock.patch("builtins.open", new_callable=mock.mock_open, read_data="{}")
@mock.patch("sonic_py_common.device_info.get_path_to_platform_dir")
@mock.patch.object(daemon_base, "db_connect")
def test_restore_app_table_all_scenarios(
    mock_connect, mock_platform_path, mock_open_, mock_sep, mock_chassis
):
    """Test all scenarios for restoring application table configurations"""
    mock_app_db = mock.Mock()
    mock_cfg_db = mock.Mock()
    mock_sta_db = mock.Mock()
    mock_connect.side_effect = [mock_app_db, mock_cfg_db, mock_sta_db]
    manager = LineCardManager(SYSLOG_IDENTIFIER, mock_chassis)

    with mock.patch.object(manager, "_add_key") as mock_add:
        mock_cfg_db.keys.side_effect = [[], ["SFP_TABLE|sfp-1"]]
        mock_cfg_db.hgetall.return_value = {"speed": "100G"}
        mock_app_db.exists.return_value = False

        mock_add.reset_mock()
        manager._restore_app_table("sfp-1")
        mock_add.assert_called_once_with(mock_app_db, "SFP_TABLE_TABLE", "sfp-1", {"speed": "100G"})

        mock_cfg_db.keys.side_effect = [[], ["SFP_TABLE|sfp-1"]]
        mock_app_db.exists.return_value = True

        mock_add.reset_mock()
        manager._restore_app_table("sfp-1")
        mock_add.assert_not_called()


# Test all delete operation scenarios
@mock.patch.object(swsscommon.SonicDBConfig, "getSeparator", return_value="|")
@mock.patch("builtins.open", new_callable=mock.mock_open, read_data="{}")
@mock.patch("sonic_py_common.device_info.get_path_to_platform_dir")
@mock.patch.object(daemon_base, "db_connect")
def test_delete_app_table_all_scenarios(
    mock_connect, mock_platform_path, mock_open_, mock_sep, mock_chassis
):
    """Test all scenarios for deleting application table configurations"""
    mock_app_db = mock.Mock()
    mock_cfg_db = mock.Mock()
    mock_sta_db = mock.Mock()
    mock_connect.side_effect = [mock_app_db, mock_cfg_db, mock_sta_db]
    manager = LineCardManager(SYSLOG_IDENTIFIER, mock_chassis)

    with mock.patch.object(manager, "_del_key") as mock_del:
        mock_app_db.keys.side_effect = [[], []]
        mock_del.reset_mock()
        manager._delete_app_table("sfp-1")
        mock_del.assert_not_called()

        mock_app_db.keys.side_effect = [[], [
            "SFP_TABLE_TABLE|sfp-1",
            "PORT_TABLE|sfp-1",
            "OTHER_TABLE|sfp-1-related"
        ]]
        mock_del.reset_mock()
        manager._delete_app_table("sfp-1")
        assert mock_del.call_count == 3
        mock_del.assert_has_calls([
            mock.call(mock_app_db, "SFP_TABLE_TABLE", "sfp-1"),
            mock.call(mock_app_db, "PORT_TABLE", "sfp-1"),
            mock.call(mock_app_db, "OTHER_TABLE", "sfp-1-related")
        ])


# Test line card manager cleanup during shutdown
@mock.patch.object(swsscommon.SonicDBConfig, "getSeparator", return_value="|")
@mock.patch("builtins.open", new_callable=mock.mock_open, read_data="{}")
@mock.patch("sonic_py_common.device_info.get_path_to_platform_dir")
@mock.patch.object(daemon_base, "db_connect")
def test_linecard_manager_deinit(
    mock_connect, mock_platform_path, mock_open_, mock_sep, mock_chassis
):
    """Test LineCardManager properly cleans up resources during shutdown"""
    mock_app_db = mock.Mock()
    mock_cfg_db = mock.Mock()
    mock_sta_db = mock.Mock()
    mock_connect.side_effect = [mock_app_db, mock_cfg_db, mock_sta_db]
    manager = LineCardManager(SYSLOG_IDENTIFIER, mock_chassis)
    mock_sta_db.keys.return_value = [
        f"{LINECARD_INFO_TABLE}|linecard-1",
        f"{LINECARD_INFO_TABLE}|linecard-2"
    ]
    mock_sta_db._del.reset_mock()
    manager.deinit()
    assert mock_sta_db._del.call_count == 2

# =================================================================
# DaemonLinecardSyncd tests
# =================================================================

@pytest.fixture
def daemon_syncd(mock_chassis):
    daemon = DaemonLinecardSyncd(SYSLOG_IDENTIFIER, mock_chassis)
    daemon.stop = mock.Mock()   # Replace Event for easier control
    return daemon


# Test daemon lifecycle operations
@mock.patch("linecardsyncd.LineCardManager")
def test_daemon_run_lifecycle(mock_mgr_cls, daemon_syncd):
    """Test daemon properly executes its lifecycle including startup and shutdown"""
    daemon_syncd.stop.wait.side_effect = [False, True]
    mock_mgr = mock.Mock()
    mock_mgr_cls.return_value = mock_mgr
    daemon_syncd.run()
    assert mock_mgr.linecard_info_update.called
    mock_mgr.deinit.assert_called_once()


# Test daemon signal handling
def test_daemon_signal_handling(daemon_syncd):
    """Test daemon properly handles various system signals"""
    linecardsyncd.exit_code = 0
    daemon_syncd.signal_handler(signal.SIGTERM, None)
    assert linecardsyncd.exit_code == 128 + signal.SIGTERM
    assert daemon_syncd.stop.set.called

    daemon_syncd.stop.set.reset_mock()
    daemon_syncd.signal_handler(signal.SIGHUP, None)
    assert not daemon_syncd.stop.set.called

# =================================================================
# Main entry tests
# =================================================================

# Test successful main execution flow
@mock.patch("linecardsyncd.get_chassis")
@mock.patch("linecardsyncd.DaemonLinecardSyncd")
@mock.patch("sys.exit")
def test_main_successful_execution(mock_exit, mock_daemon_cls, mock_get_chassis):
    """Test main() function executes successfully with proper daemon initialization"""
    mock_chassis = mock.Mock()
    mock_daemon = mock.Mock()
    mock_get_chassis.return_value = mock_chassis
    mock_daemon_cls.return_value = mock_daemon
    linecardsyncd.main()
    mock_daemon.run.assert_called_once()
    mock_exit.assert_called_once_with(linecardsyncd.exit_code)


# Test main execution failure handling
@mock.patch("linecardsyncd.get_chassis", side_effect=SystemExit(CHASSIS_LOAD_ERROR))
def test_main_chassis_initialization_failure(mock_get_chassis):
    """Test main() function handles chassis initialization failures appropriately"""
    with pytest.raises(SystemExit) as exc_info:
        linecardsyncd.main()
    assert exc_info.value.code == CHASSIS_LOAD_ERROR
