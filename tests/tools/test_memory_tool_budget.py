"""Capacity errors give an actionable budget without mutating memories or prompts."""

import json

import pytest

from tools.memory_tool import ENTRY_DELIMITER, MEMORY_SCHEMA, MemoryStore, memory_tool


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr("tools.memory_tool.get_memory_dir", lambda: tmp_path)
    result = MemoryStore()
    result.load_from_disk()
    return result


@pytest.mark.parametrize("target", ["memory", "user"])
def test_near_full_replacement_reports_exact_budget_and_retry_preserves_entries(store, target):
    # Reproduce the observed failure: a 134-char entry, two spare chars,
    # and a proposed 197-char replacement. No production memories are read.
    original = (
        "Narrow tested edits; scoped/supervised open-weight agents; no third-party code. "
        "Token-saving tools/skills should span future projects."
    )
    limit = store._char_limit(target)
    unrelated = "U" * (limit - 2 - len(original) - len(ENTRY_DELIMITER))
    assert store.add(target, unrelated)["success"]
    assert store.add(target, original)["success"]
    store.load_from_disk()
    path = store._path_for(target)
    before = path.read_bytes()
    snapshot = store.format_for_system_prompt(target)

    result = json.loads(memory_tool(
        action="replace", target=target, old_text="Narrow tested edits;",
        content="R" * 197, store=store,
    ))
    assert result["success"] is False
    assert result["max_content_chars"] == 136
    assert "136" in result["error"]
    assert path.read_bytes() == before
    assert store._entries_for(target) == [unrelated, original]
    assert store.format_for_system_prompt(target) == snapshot

    # Use the reported budget, retaining all four existing preferences.
    replacement = (
        "Narrow tested edits; scoped/supervised open-weight agents; no third-party code. "
        "Token-saving tools/skills should span future projects!"
    )
    replacement += "!" * (result["max_content_chars"] - len(replacement))
    retry = store.replace(target, "Narrow tested edits;", replacement)
    assert retry["success"] is True
    assert store._entries_for(target) == [unrelated, replacement]
    assert store._char_count(target) == limit
    assert path.read_text() == ENTRY_DELIMITER.join([unrelated, replacement])
    assert store.format_for_system_prompt(target) == snapshot


@pytest.mark.parametrize("target", ["memory", "user"])
@pytest.mark.parametrize("existing", [[], ["Résumé ☕"], ["first", "second"]])
def test_add_budget_accounts_for_delimiter_and_characters_not_bytes(store, target, existing):
    limit = 32
    if target == "user":
        store.user_char_limit = limit
    else:
        store.memory_char_limit = limit
    for entry in existing:
        assert store.add(target, entry)["success"]
    expected = limit - len(ENTRY_DELIMITER.join(existing)) - (len(ENTRY_DELIMITER) if existing else 0)
    result = store.add(target, "é" * (expected + 1))
    assert result["success"] is False
    assert result["max_content_chars"] == expected
    assert store._entries_for(target) == existing
    # Input whitespace is stripped before the character budget is enforced.
    assert store.add(target, "  " + "é" * expected + "\n")["success"]
    assert store._char_count(target) == limit
    assert store._entries_for(target) == existing + ["é" * expected]


@pytest.mark.parametrize("target", ["memory", "user"])
def test_no_room_for_add_reports_zero_without_deleting_or_truncating(store, target):
    content = "A" * (store._char_limit(target) - 2)
    assert store.add(target, content)["success"]
    before = store._path_for(target).read_bytes()
    result = store.add(target, "new preference")
    assert result["success"] is False
    assert result["max_content_chars"] == 0
    assert store._path_for(target).read_bytes() == before
    assert store._entries_for(target) == [content]


@pytest.mark.parametrize("target", ["memory", "user"])
def test_replacement_budget_uses_live_disk_after_another_store_writes(store, target):
    original = "User prefers tea"
    assert store.add(target, original)["success"]
    other = MemoryStore()
    other.load_from_disk()
    assert other.add(target, "User prefers quiet workspaces")["success"]
    before = store._path_for(target).read_bytes()
    result = store.replace(target, "prefers tea", "Z" * store._char_limit(target))
    assert result["success"] is False
    expected = store._char_limit(target) - len(ENTRY_DELIMITER.join(other._entries_for(target))) + len(original)
    assert result["max_content_chars"] == expected
    assert store._path_for(target).read_bytes() == before
    assert store._entries_for(target) == other._entries_for(target)


def test_replacement_budget_counts_entire_matched_entry_not_selector(store):
    original = "Tea and coffee; café ☕"
    assert store.add("user", original)["success"]
    assert store.add("user", "Unrelated preference")["success"]
    result = store.replace("user", "café", "X" * 1400)
    expected = store.user_char_limit - store._char_count("user") + len(original)
    assert result["max_content_chars"] == expected
    assert store.replace("user", "café", "é" * expected)["success"]
    assert store._char_count("user") == store.user_char_limit


def test_schema_guides_capacity_planning_and_preserves_unrelated_preferences():
    description = MEMORY_SCHEMA["description"]
    assert "consolidate before adding" in description
    assert "len(content.strip())" in description
    assert "max_content_chars" in description
    assert "unrelated" in description
    assert "still-valid" in description
    assert "Never silently truncate or delete" in description
