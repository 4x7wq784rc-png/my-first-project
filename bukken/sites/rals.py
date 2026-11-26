"""不動産投資連合隊（収益物件）

ENABLED = False の理由（2026-11 確認）:
  - https://rengotai.rals.co.jp/ は加盟店（不動産会社）向けの広告掲載案内サイトで、物件一覧は無い。
    robots.txt は全許可・sitemap.xml（fo-pro.s3... に転送）も会社案内・コラム・資料DLのページのみ。
  - 物件検索の本体は https://www.rals.co.jp/invest/ → 301 → https://www.rals.net/invest
    （首都圏版も www.rals.net/tokyo/ 等）にあるが、この実行環境のネットワーク設定で
    www.rals.net への接続がプロキシに拒否される（サイト側のブロックや robots.txt による禁止ではない）。
  環境で www.rals.net を許可すれば、robots.txt を確認したうえで一覧ページを解析して実装可能。
"""
from ..common import Listing

NAME = "不動産投資連合隊"
ENABLED = False


def collect(log=print) -> list[Listing]:
    log(f"  {NAME}: 未対応（物件一覧がある www.rals.net に接続できないため）")
    return []
