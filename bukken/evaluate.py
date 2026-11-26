"""賃貸併用向きかどうかの判定。A=有力 / B=検討 / None=対象外"""
from . import config
from .common import Listing, norm, ward_of


def _has_kw(l: Listing) -> list[str]:
    text = norm(" ".join([l.title, l.extra]))
    return [k for k in config.HEIYO_KEYWORDS if k in text]


def evaluate(l: Listing) -> Listing | None:
    if not ward_of(l.address) and not ward_of(l.title):
        return None
    r: list[str] = []
    walk = l.walk_min
    if walk is not None and walk > config.WALK_MAX_MIN:
        return None

    if l.kind == "土地":
        if l.price_man is None or l.price_man > config.LAND_MAX_MAN:
            return None
        if l.land_m2 is not None and l.land_m2 < config.LAND_MIN_M2:
            return None
        floor = l.land_m2 * l.yoseki / 100 if (l.land_m2 and l.yoseki) else None
        if floor is not None and floor < config.FLOOR_MIN_M2:
            return None
        score = 0
        if floor is not None:
            r.append(f"建てられる延床 約{floor:.0f}㎡")
            score += 2 if floor >= config.FLOOR_TARGET_M2 else 1
        else:
            r.append("容積率不明（要確認）")
        if walk is None:
            r.append("バス便または徒歩不明")
        elif walk <= config.WALK_GOOD_MIN:
            r.append(f"駅徒歩{walk}分")
            score += 2
        else:
            r.append(f"駅徒歩{walk}分（やや遠い）")
            score += 1
        if "建築条件" in l.title + l.extra and "建築条件なし" not in l.title + l.extra \
                and "建築条件無" not in l.title + l.extra and "建築条件の無い" not in l.title + l.extra:
            r.append("建築条件付き（併用住宅が建てられるか要交渉）")
            score -= 2
        l.rank = "A" if score >= 4 else "B"
    else:
        if l.price_man is None or l.price_man > config.TOTAL_MAX_MAN:
            return None
        kws = _has_kw(l)
        big = l.building_m2 is not None and l.building_m2 >= config.BIG_BUILDING_M2
        if l.kind == "収益・併用" or kws:
            r.append("キーワード: " + "・".join(kws) if kws else "収益・併用物件")
            l.rank = "A" if (walk is not None and walk <= config.WALK_GOOD_MIN) else "B"
        elif big:
            r.append(f"建物{l.building_m2:.0f}㎡（改装・建替えで併用化の余地）")
            l.rank = "B"
        else:
            return None
        if walk is not None:
            r.append(f"駅徒歩{walk}分")
        else:
            r.append("バス便または徒歩不明")
    l.reasons = r
    return l
