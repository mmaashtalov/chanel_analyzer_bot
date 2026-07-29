import pytest
from app.workspaces.models import Workspace, WorkspaceItem, WorkspaceItemType
from app.workspaces.service import WorkspaceValidationError, normalize_item, normalize_workspace_name


def test_workspace_name_normalization():
    assert normalize_workspace_name("  ОПК   мониторинг ") == "ОПК мониторинг"
    with pytest.raises(WorkspaceValidationError): normalize_workspace_name("x")


def test_channel_normalization():
    assert normalize_item(WorkspaceItemType.CHANNEL, "https://t.me/Example_Channel") == "example_channel"
    with pytest.raises(WorkspaceValidationError): normalize_item(WorkspaceItemType.CHANNEL, "bad!")


def test_domain_and_rss_normalization():
    assert normalize_item(WorkspaceItemType.DOMAIN, "https://www.Example.com/a") == "example.com"
    assert normalize_item(WorkspaceItemType.RSS, "HTTPS://Example.com/feed#x") == "https://example.com/feed"


def test_item_type_aliases():
    assert WorkspaceItemType.parse("канал") is WorkspaceItemType.CHANNEL
    assert WorkspaceItemType.parse("keyword") is WorkspaceItemType.KEYWORD


def test_workspace_counts():
    workspace = Workspace("1", 10, "Test", None, True, (
        WorkspaceItem("1", WorkspaceItemType.CHANNEL, "@a", "a"),
        WorkspaceItem("2", WorkspaceItemType.DOMAIN, "x.ru", "x.ru"),
        WorkspaceItem("3", WorkspaceItemType.DOMAIN, "y.ru", "y.ru"),
    ))
    assert workspace.counts()["domain"] == 2
    assert workspace.counts()["channel"] == 1
