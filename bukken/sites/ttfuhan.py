"""東京建物不動産販売

ENABLED = False の理由（2026-11 確認）:
  - https://www.ttfuhan.co.jp/ は会社サイト（robots.txt は 404 = 制限なし）で、物件一覧は無い。
    物件検索は別ホスト https://sumikae.ttfuhan.co.jp/buy/（土地・戸建て）と /investment/（投資用）。
  - sumikae.ttfuhan.co.jp の robots.txt は取得でき（200）、/buy/search/result/・/tochi/list/・/kodate/list/・
    /buy/used_*_detail.php 等を禁止している。
  - しかしトップページ・/buy/・/investment/ を含む通常のページはすべてサーバー（nginx）が
    HTTP 403（本文なし）を返す。ブラウザ相当の User-Agent でも同じで、この接続元からのアクセスを
    サイト側が拒否していると判断。回避（ヘッダー偽装・ヘッドレスブラウザ等）はしない方針のため未対応。
    また、一覧系の URL（/buy/search/result/ 等）は robots.txt で禁止されているので、
    仮に 403 が解消されても許可された一覧ページがあるか要確認。
"""
from ..common import Listing

NAME = "東京建物不動産販売"
ENABLED = False


def collect(log=print) -> list[Listing]:
    log(f"  {NAME}: 未対応（sumikae.ttfuhan.co.jp がHTTP 403 で拒否するため）")
    return []
