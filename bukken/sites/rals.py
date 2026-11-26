"""不動産投資連合隊（収益物件）

ENABLED = False の理由:
  物件検索は別ホスト https://rengotai.rals.co.jp/ にあり（www.rals.co.jp は会社サイトで物件一覧なし）、
  この実行環境のネットワーク設定（許可ホスト一覧）で rengotai.rals.co.jp への接続が拒否されるため、
  一覧ページの構造を確認できず実装できていない（サイト側のブロックや robots.txt による禁止ではない）。
  www.rals.co.jp/robots.txt は一般のクローラーに Allow: /。
  環境で rengotai.rals.co.jp を許可すれば、robots.txt を確認したうえで実装可能。
"""
from ..common import Listing

NAME = "不動産投資連合隊"
ENABLED = False


def collect(log=print) -> list[Listing]:
    log(f"  {NAME}: 未対応（rengotai.rals.co.jp に接続できないため）")
    return []
