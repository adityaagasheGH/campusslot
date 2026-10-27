import threading

import pytest

import accounts
import storage
from conftest import TOMORROW, book


def test_second_booking_of_same_slot_refused_with_taken_slots(tokens):
    assert book(tokens["alice"], slots=["1000"])[0] == 201
    status, body = book(tokens["bob"], slots=["0930", "1000", "1030"])
    assert status == 409
    assert body["error"]["reason"] == "SLOT_TAKEN"
    assert body["error"]["takenSlots"] == ["1000"]


def test_refused_request_releases_the_locks_it_got(tokens):
    book(tokens["alice"], slots=["1030"])
    assert book(tokens["bob"], slots=["1000", "1030"])[0] == 409
    keys = storage.list_keys(f"locks/study-room-1/{TOMORROW}/")
    assert keys == [f"locks/study-room-1/{TOMORROW}/1030"]   # bob's 1000 lock was removed
    assert book(tokens["bob"], slots=["1000"])[0] == 201


def _race(users_tokens):
    results = []
    barrier = threading.Barrier(len(users_tokens))

    def go(tok):
        barrier.wait()
        results.append(book(tok, slots=["1500"])[0])

    threads = [threading.Thread(target=go, args=(t,)) for t in users_tokens]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


@pytest.fixture
def nine_students(aws):
    out = []
    for i in range(9):
        u = accounts.make_user(f"racer{i}@campus.test", f"Racer {i}", "student", "racing-pass-1", 1000)
        accounts.save_new_user(u)
        out.append(accounts.issue_token(u))
    return out


@pytest.mark.parametrize("run", range(5))
def test_nine_simultaneous_requests_exactly_one_wins(nine_students, run):
    results = _race(nine_students)
    assert sorted(results) == [201] + [409] * 8
    assert len(storage.list_keys("bookings/")) == 1


def test_without_the_guard_double_booking_happens(nine_students, monkeypatch):
    """Proof the If-None-Match condition is what prevents double booking."""
    real = storage.put_json
    monkeypatch.setattr(storage, "put_json",
                        lambda key, obj, if_none_match=False, if_match=None:
                        real(key, obj, if_none_match=if_none_match and not key.startswith("locks/"), if_match=if_match))
    results = [book(t, slots=["1500"])[0] for t in nine_students[:2]]
    assert results == [201, 201]  # both "succeed": exactly what the guard stops


def test_lock_is_created_with_if_none_match(tokens, monkeypatch):
    seen = []
    real = storage.put_json

    def spy(key, obj, if_none_match=False, if_match=None):
        seen.append((key, if_none_match))
        return real(key, obj, if_none_match, if_match)

    monkeypatch.setattr(storage, "put_json", spy)
    book(tokens["alice"], slots=["1000"])
    assert (f"locks/study-room-1/{TOMORROW}/1000", True) in seen
