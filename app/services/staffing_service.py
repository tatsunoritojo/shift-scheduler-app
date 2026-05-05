"""Staffing requirement service.

組織ごとの曜日 × 時間帯の必要人数を管理する。OpeningHours が
「店が開いている時間」を表すのに対し、StaffingRequirement は
「その時間帯に何人いてほしいか」を表す。両者は意味が独立しているので
別テーブルとして管理する。

シフト構築画面では、ここから取得した requirements と Admin が
割り当てた entries を組み合わせて、時間帯ごとの過不足を可視化する。
"""

from app.extensions import db
from app.models.staffing import StaffingRequirement
from app.utils.validators import validate_time_str


def get_requirements(org) -> list[dict]:
    """組織の必要人数設定を曜日順 + 時刻順で返す。"""
    rows = (StaffingRequirement.query
            .filter_by(organization_id=org.id)
            .order_by(StaffingRequirement.day_of_week, StaffingRequirement.start_time)
            .all())
    return [r.to_dict() for r in rows]


def set_requirements(org, items: list[dict]) -> list[dict]:
    """必要人数設定を一括更新（既存全削除 → 新規 insert）。

    items: [{day_of_week, start_time, end_time, required_count}]

    バリデーション失敗時は ValueError を投げ、呼び出し側で 400 に変換する。
    DB エラーは呼び出し側で rollback。
    """
    normalized = _validate_items(items)

    # 既存全削除 → 新規 insert（一括 upsert として最もシンプル）
    StaffingRequirement.query.filter_by(organization_id=org.id).delete()
    for item in normalized:
        db.session.add(StaffingRequirement(
            organization_id=org.id,
            day_of_week=item['day_of_week'],
            start_time=item['start_time'],
            end_time=item['end_time'],
            required_count=item['required_count'],
        ))
    db.session.flush()
    return get_requirements(org)


def get_demand_for_weekday(org, day_of_week: int) -> list[dict]:
    """指定曜日に該当する必要人数を時間帯別に返す。

    シフト構築画面で「日付 → 曜日 → 必要人数」を導出するときに使う。
    """
    rows = (StaffingRequirement.query
            .filter_by(organization_id=org.id, day_of_week=day_of_week)
            .order_by(StaffingRequirement.start_time)
            .all())
    return [r.to_dict() for r in rows]


def _validate_items(items) -> list[dict]:
    """入力リストを正規化して返す。失敗時 ValueError。"""
    if not isinstance(items, list):
        raise ValueError("items must be a list")
    normalized = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"items[{i}] must be an object")
        try:
            day = int(item.get('day_of_week'))
        except (TypeError, ValueError):
            raise ValueError(f"items[{i}].day_of_week must be an integer")
        if day < 0 or day > 6:
            raise ValueError(f"items[{i}].day_of_week must be 0-6")

        start = item.get('start_time')
        end = item.get('end_time')
        validate_time_str(start, f"items[{i}].start_time")
        validate_time_str(end, f"items[{i}].end_time")
        if start >= end:
            raise ValueError(f"items[{i}].start_time must be before end_time")

        try:
            count = int(item.get('required_count'))
        except (TypeError, ValueError):
            raise ValueError(f"items[{i}].required_count must be an integer")
        if count < 0:
            raise ValueError(f"items[{i}].required_count must be >= 0")
        if count > 999:
            raise ValueError(f"items[{i}].required_count too large (max 999)")

        normalized.append({
            'day_of_week': day,
            'start_time': start,
            'end_time': end,
            'required_count': count,
        })

    # 同一曜日内のスロット重複を検出（OpeningHours 単一スロットと違い時間帯
    # 分割を許可するため、編集ミスで [09-13] と [11-15] のような重なりが
    # 入りうる。データ整合性のため弾く。HH:MM 文字列は左ゼロ埋めなので
    # lexicographic 比較で時刻順序判定が安全に成立する）
    by_day: dict[int, list[tuple[int, dict]]] = {}
    for idx, item in enumerate(normalized):
        by_day.setdefault(item['day_of_week'], []).append((idx, item))
    for day, slots in by_day.items():
        if len(slots) < 2:
            continue
        slots_sorted = sorted(slots, key=lambda pair: pair[1]['start_time'])
        for k in range(len(slots_sorted) - 1):
            a_idx, a = slots_sorted[k]
            b_idx, b = slots_sorted[k + 1]
            if a['end_time'] > b['start_time']:
                raise ValueError(
                    f"items[{b_idx}] overlaps with items[{a_idx}] on day_of_week={day}"
                )

    return normalized
