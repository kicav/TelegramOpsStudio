from telegram_workflow.security.secret_store import MemorySecretStore


def test_memory_secret_store_contract() -> None:
    store = MemorySecretStore()
    store.set("api/main", "secret")
    assert store.get("api/main") == "secret"
    store.delete("api/main")
    assert store.get("api/main") is None
