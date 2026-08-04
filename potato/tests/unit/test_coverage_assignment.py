from potato.item_state_management import ItemStateManager
from potato.user_state_management import InMemoryUserState


def manager_with_items(count=4, target=2):
    manager = ItemStateManager({
        "assignment_strategy": "least_annotated",
        "num_annotators_per_item": target,
        "max_annotations_per_user": -1,
    })
    manager.add_items({
        f"item_{index}": {"id": f"item_{index}", "text": str(index)}
        for index in range(1, count + 1)
    })
    return manager


def user(user_id, quota):
    state = InMemoryUserState(user_id)
    state.set_max_assignments(quota)
    return state


def assigned_users_by_item(users):
    result = {}
    for state in users:
        for item_id in state.get_assigned_instance_ids():
            result.setdefault(item_id, set()).add(state.get_user_id())
    return result


def test_coverage_fill_assigns_full_user_quotas_without_three_item_batches():
    manager = manager_with_items(count=4, target=2)
    users = [user("a", 3), user("b", 3), user("c", 2)]

    report = manager.fill_assignments_to_coverage(users)

    coverage = assigned_users_by_item(users)
    assert {item_id: len(names) for item_id, names in coverage.items()} == {
        "item_1": 2,
        "item_2": 2,
        "item_3": 2,
        "item_4": 2,
    }
    assert {state.get_user_id(): state.get_assigned_instance_count() for state in users} == {
        "a": 3,
        "b": 3,
        "c": 2,
    }
    assert report["new_assignments"] == 8
    assert report["total_shortfall"] == 0


def test_coverage_fill_continues_to_each_user_m_after_minimum_n_is_met():
    manager = manager_with_items(count=4, target=1)
    users = [user("a", 3), user("b", 3)]

    report = manager.fill_assignments_to_coverage(users)

    assert [state.get_assigned_instance_count() for state in users] == [3, 3]
    assert report["new_assignments"] == 6
    assert report["total_shortfall"] == 0


def test_coverage_fill_reports_shortage_when_user_capacity_is_insufficient():
    manager = manager_with_items(count=3, target=2)
    users = [user("a", 2), user("b", 1)]

    report = manager.fill_assignments_to_coverage(users)

    assert report["new_assignments"] == 3
    assert report["total_shortfall"] == 3
    assert sum(row["missing"] for row in report["items_below_target"]) == 3


def test_coverage_fill_preserves_existing_assignments_and_never_duplicates_user():
    manager = manager_with_items(count=2, target=2)
    users = [user("a", 2), user("b", 2)]
    users[0].assign_instance(manager.get_item("item_1"))

    report = manager.fill_assignments_to_coverage(users)

    coverage = assigned_users_by_item(users)
    assert coverage["item_1"] == {"a", "b"}
    assert coverage["item_2"] == {"a", "b"}
    assert report["new_assignments"] == 3


def test_zero_quota_user_is_not_assigned():
    manager = manager_with_items(count=1, target=1)
    admin = user("admin", 0)
    annotator = user("worker", 1)

    manager.fill_assignments_to_coverage([admin, annotator])

    assert admin.get_assigned_instance_count() == 0
    assert annotator.get_assigned_instance_ids() == {"item_1"}


def test_coverage_report_lists_assigned_accounts_and_missing_slots():
    manager = manager_with_items(count=2, target=2)
    users = [user("a", 1), user("b", 1)]
    users[0].assign_instance(manager.get_item("item_1"))
    users[1].assign_instance(manager.get_item("item_1"))

    report = manager.get_assignment_coverage(users)

    assert report["items"]["item_1"] == {
        "assigned_users": ["a", "b"],
        "assigned": 2,
        "target": 2,
        "missing": 0,
    }
    assert report["items"]["item_2"]["missing"] == 2
    assert report["total_shortfall"] == 2
