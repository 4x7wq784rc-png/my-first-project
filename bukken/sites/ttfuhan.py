"""東京建物不動産販売

ENABLED = False の理由（2026-11 確認）:
  - https://www.ttfuhan.co.jp/ は会社サイト（robots.txt は 404 = 制限なし）で、物件一覧は無い。
    「買う」ページ（/services/buy/）から物件検索は別ホストへリンクされている:
      https://sumikae.ttfuhan.co.jp/buy/（土地・戸建て等）, https://sumikae.ttfuhan.co.jp/investment/（投資用）
  - この実行環境のネットワーク設定で sumikae.ttfuhan.co.jp への接続がプロキシに拒否されるため、
    robots.txt も一覧ページの構造も確認できず実装できていない（サイト側のブロックではない）。
  環境で sumikae.ttfuhan.co.jp を許可すれば、robots.txt を確認したうえで実装可能。
"""
from ..common import Listing

NAME = "東京建物不動産販売"
ENABLED = False


def collect(log=print) -> list[Listing]:
    log(f"  {NAME}: 未対応（物件検索の sumikae.ttfuhan.co.jp に接続できないため）")
    return []
