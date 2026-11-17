# 分類規則與整理範圍

分類器用 `classifier_rules.json` 決定哪些郵件轉寄至 Gmail。它回傳 `forward` 或 `junk`，並記錄命中原因。無法確定的郵件預設轉寄。分類結果不會直接刪除 POP3 原件，刪除仍由保留期限與清理流程負責。

## 先命中的規則決定結果

| 順序 | 規則 | 結果 |
|---|---|---|
| 1 | `ignore_patterns` 的寄件者與選填主旨 | `junk` |
| 2 | `sender_content_rules` | 同一寄件者先保留提醒，再阻擋促銷，其餘轉寄 |
| 3 | `always_junk_senders`、`always_junk_subjects`、`always_junk_subject_groups` | `junk` |
| 4 | `always_forward_senders`、`always_forward_subjects` | `forward` |
| 5 | `promo_senders` 加群發標頭 | `junk` |
| 6 | 寄件者或主旨含 `important_header_terms` | `forward` |
| 7 | 寄件者、主旨或正文含 `junk_terms`，且有群發標頭或促銷寄件者 | `junk` |
| 8 | 其餘郵件 | `forward` |

明確阻擋偏好優先於保留偏好及一般重要提示。已知促銷寄件者加群發標頭，也優先於一般重要提示。整理規則沒有調換這些順序。

## 字詞與群組的比對方式

規則載入時轉成小寫。永久寄件者與主旨偏好、`ignore_patterns`、`sender_content_rules` 維持子字串比對，因此主旨清單中的片語不必與完整主旨相等。寄件者清單比對整個 `From` 標頭，包含顯示名稱，並非經驗證的寄件者身分。

`important_header_terms` 對純 ASCII 單字及空格連接的片語使用英數字邊界。`ntu` 不會命中 `intuit`。非 ASCII 或含標點的片語仍使用子字串比對。

`marketing_match_mode` 僅控制 `promo_senders` 與一般 `junk_terms`。舊自訂規則的預設值是 `substring`，內建規則明確設為 `words`，沿用相同的 ASCII 英數字邊界。`nova` 不會命中 `Innovation`，`cart` 不會命中 `Cartography`。永久偏好與 TurboTax 的寄件者內容規則不受這個設定影響。未知模式會在載入時引發 `ValueError`。

`always_junk_subject_groups` 表示主旨中的條件組合。

| 欄位 | 意義 |
|---|---|
| `all` | 每個字詞都必須命中 |
| `any` | 若非空，至少一個字詞必須命中 |
| `match_mode` | 預設 `substring`。`words` 沿用重要提示的 ASCII 英數字邊界 |
| `reason` | 選填的分類原因 |

`all` 與 `any` 使用同一個比對模式。`words` 不做詞幹分析，`conference` 不會命中 `conferences`，須分別列出。中文與含標點片語仍維持子字串語意。空的 `all` 沒有必要條件，空的 `any` 沒有替代條件，因此兩者皆空的群組會匹配所有主旨。

舊自訂規則沒有 `match_mode` 時，保留子字串比對。未知模式會在載入規則時引發 `ValueError`。沒有全面改成詞界比對，是為了保留既有自訂規則的語意。

## 整份規則的審查結論

| 區塊 | 整理與保留理由 |
|---|---|
| `important_header_terms` | 移除已由 `security` 涵蓋的 `security alert`。保留學校、銀行、安全、旅行、求職與配送線索，因為它們用來保護重要信件。它們不代表已驗證身分或信件內容。 |
| `junk_terms` | 移除已由 `優惠` 涵蓋的 `旅遊優惠`。啟用詞界比對，避免 `cart` 誤命中地圖學。詞界下 `promotion`、`deals` 不再冗餘，因此保留並明列常用詞形。歷史資料另支持三個完整寄件地址作為特定線索，維持重要提示之後的判斷順序。一般促銷線索仍須搭配群發或已知促銷寄件者，單一垃圾字詞不直接阻擋。 |
| `promo_senders` | 移除 `hsbc taiwan`、`jr九州`、`jrkyushu`、`instapaper`，因為較早的永久阻擋已涵蓋它們。啟用詞界比對，避免 `nova` 誤命中 Innovation。加入既有測試已出現的 `packtpub.com`，補足只有網域、沒有 Packt 顯示名稱的情形。沒有觀測依據的品牌網域不猜測。 |
| `always_forward_senders` | 移除已由 `initium.com` 子字串涵蓋的 `theinitium.com`。保留端傳媒、Giloo 與 Slack 偏好，不能因為同樣有退訂標頭就當成一般廣告。 |
| `always_forward_subjects` | 保留電子發票核對通知特例。沒有證據支持把所有發票相關主旨都設成永久保留。 |
| `always_junk_senders` | 保留已確認的寄件者偏好。未推廣成所有銀行、交通或配送通知，避免改變正常帳務與配送信的處理。 |
| `always_junk_subjects` | 健康完整文章改為具名系列加全形或半形冒號。保留 Recruit ID、日本表單與出口文件原完整片語，它們已有明確偏好，不能推廣成所有登入、表單或貿易文件。 |
| `always_junk_subject_groups` | CFP 改成選用詞界模式，明列會議與工作坊的單複數，修正 CFPB 等字片誤擋。出口文件新增兩個文件片語加明確招攬片語的合取群組，涵蓋格式與順序變化。 |
| `ignore_patterns` | 保留 Google 特定安全通知、NTU 中英文隔離通知與 AtCoder 偏好。相同寄件者的其他主旨仍有不同用途。中英文隔離通知是兩個必要語言變體，未為合併它們增加新結構。 |
| `sender_content_rules` | 保留 TurboTax 的提醒優先順序與不確定時轉寄，僅移除已由 `savings` 涵蓋的 `bigger tax savings`。稅務期限與促銷同時出現時，不能套用一般促銷阻擋。 |
| `bulk_headers` | 保留現有標頭清單。`Precedence` 去除前後空白並轉小寫後，只有 `bulk`、`list`、`junk` 算群發，`personal`、未知值或空白不算。其他標頭維持值非空即為線索。群發線索單獨不構成阻擋。 |

移除冗餘字詞可能縮短 `reason` 中列出的字詞，不改變該項清理的分類決策。永久寄件者偏好的子字串比對維持原狀，只有行銷清單選用詞界模式。

詞界比對不做詞幹分析。`newsletter`、`coupon`、`discount`、`sale`、`reward` 分別明列其常用複數，`promo` 另列 `promotion`、`promotions`、`promotional`，`deal` 與 `deals` 均保留。這些詞形是用合成案例驗證的維護選擇，並非新觀測的真實郵件。未明列的不明詞形依其餘規則判斷，無明確證據時轉寄。

## 通用規則仍需要邊界

健康系列僅使用 `天然保健专家：` 與 `天然保健专家:` 兩個具名片語，沿用主旨子字串比對。一般健康研究、專家討論或沒有分隔符的相似名稱仍轉寄。這次只有原始「天然保健专家：诚实可改善健康」是使用者確認案例，同系列其他文章是有界泛化的政策選擇，測試使用合成變體。引用這個具名片語的主旨也可能命中，規則沒有理解引用語意。

出口文件新群組要求主旨同時出現 `certificate of origin` 與 `export documentation`，再搭配 `documentation agent`、`documentation agents`、`service available` 或 `services available`。僅有 `agent` 或 `service` 太寬，正常交付文件給代理商或詢問客服也會出現這些詞，因此不用它們作為招攬條件。

原本的 `certificate of origin/export documentation` 完整片語特例保留，承接已確認的阻擋偏好。新群組補充斜線空格、其他分隔符與顛倒順序的招攬變體。一般文件交付沒有招攬片語時仍轉寄，但既有完整片語特例仍會優先命中。

這些規則不能證明主旨的實際意圖。新增招攬片語也可能出現在正常往來，因此合成正反例只能證明已列出的邊界，不能宣稱已量得真實郵件的全域誤擋率。

## 歷史資料提供的依據與限制

本次歷史盤點共有 2,279 筆具備寄件者與主旨的紀錄，其中 1,520 筆的分類原因明確含有群發線索。這些資料沒有正文及完整郵件標頭，因此只能檢查部分 metadata 的規則行為，不能當成完整原信重播。舊分類也不是人工標註的正確答案，行為一致不等於分類準確率已獲驗證。

健康具名系列只有一個實例，出口文件有兩個，CFP 有四個。新增文章、標點、順序及詞界變體仍來自合成案例，不能描述成多封實際郵件已證明整個新範圍。

詞界清理會讓寄件地址內的 `marketing` 或 `sale` 字片失去原本的線索。歷史資料中 Hertz 有七筆旅遊促銷，其中三筆在詞界模式下失去寄件者線索；myeurolinks 有兩筆來自不同子網域的運輸價格招攬。因此補入以下完整地址。

- `asiamarketing@emails.hertz.com`
- `sale02@logistics.myeurolinks.com`
- `sale02@rail.myeurolinks.com`

這些地址放在 `junk_terms`，沿用一般重要提示之後的判斷，仍需要群發或已知促銷寄件者條件。它們沒有加入永久阻擋或提早執行的促銷寄件者清單，也沒有擴成整個網域。固定案例以合成顯示名稱與主旨，確認這些地址的群發中性通知維持阻擋，但收據、安全、配送、非群發，以及相同網域的其他未知地址仍可轉寄。

在保留相同本機特例的前提下，以寄件者、主旨與原因中可證實的群發線索重建這 2,279 筆部分資料，補入地址後的新舊決策相同。僅使用寄件者與主旨時有兩筆由阻擋變成轉寄，補回已記錄的群發線索後仍會阻擋。這些比較沒有還原正文或未知標頭，不能當成真實郵件準確率。

公開 fixture 使用合成顯示名稱與主旨，沒有複製歷史郵件主旨、UID 或使用者地址。

## 重跑離線驗證

從儲存庫根目錄執行全部測試。

```sh
uv run --locked python -m unittest discover -s tests
```

固定案例儲存在 `tests/fixtures/classifier_rule_review.json`，包含已確認主旨、既有測試形狀與合成變體。每個案例獨立列出整理前後的預期決策。測試經由 `Classifier.classify()` 檢查目前決策，不接觸 POP3、SMTP、真實郵件或處理狀態。

```sh
uv run --locked python tests/review_classifier_rules.py
```

要比較整理前後的完整行為，先準備整理前的受信任 checkout，再指定其根目錄。比較工具透過目前 Python 直譯器啟動一個子行程，以該目錄為工作目錄，載入舊分類器與舊規則，並一次取得所有案例的舊決策。它不使用 shell。指定目錄會執行其中的 Python 程式，因此只使用自己信任的 checkout。

```sh
git worktree add --detach /tmp/ntu-classifier-before 6c5e4ef
uv run --locked python tests/review_classifier_rules.py --baseline-root /tmp/ntu-classifier-before
```

這份基底是加入原始健康主旨後、進行本次清理前的程式與規則。工具分別檢查案例的 `before` 與 `after` 預期，任何不符都回傳非零狀態。`Precedence` 的改變在程式中，僅以新程式載入舊 JSON 無法代表原始行為，因此不提供這種不完整的比較模式。
