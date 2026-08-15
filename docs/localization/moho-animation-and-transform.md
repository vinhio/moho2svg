# Mô hình Hoạt ảnh và Transform của Moho

> Bản dịch tiếng Việt của `docs/moho-animation-and-transform.md`. Bản tiếng Anh là nguồn tham chiếu chính thức.

Moho không hoạt ảnh theo từng frame. Nó lưu một số ít **keyframe** cho mỗi
thuộc tính và để chương trình tính mọi frame ở giữa. Phần lớn chuyển động trong
một tài liệu Moho thật thậm chí không nằm trên artwork: nó nằm trên một
**bộ xương (skeleton)**, và artwork đi theo các bone qua một ngăn xếp
transform.

Tài liệu này giải thích mô hình đó: thời gian được lưu thế nào, một giá trị ở
một frame bất kỳ được tạo ra ra sao, chuyển động thực sự đến từ đâu trong các
file thật, và ngăn xếp transform biến tất cả thành một điểm trên canvas như
thế nào.

Các tài liệu đồng hành:

- `moho-project-file-format.md` — tham chiếu đầy đủ các trường của định dạng file.
- `moho-rigging-and-deformation.md` — hệ thống bone chuyên sâu (constraints,
  control bones, IK, dynamics), Smart Warp, và các trường cấp mesh ràng buộc
  biến dạng.
- `moho-export-pipeline.md` — cách `moho2svg.py` duyệt một tài liệu và sinh ra SVG.
- `moho-exporting-svg.md` — cách dùng dòng lệnh.

Tài liệu này không lặp lại những tài liệu đó. Nó chỉ tập trung vào thời gian và
transform, và bổ sung công việc giải mã mà các tài liệu khác đánh dấu là chưa
biết.

---

## 1. Phạm vi và cơ sở bằng chứng

Mọi con số ở đây được đo từ 19 file dự án trong thư mục (bị gitignore) `moho/`:
17 file `.animeproj` (định dạng phiên bản 1021 và 1038) và 2 file `.mohoproj`
(1038 và 1045). Không có gì trích dẫn từ tài liệu của chính Moho.

Phương pháp đo quan trọng, vì nó thay đổi các con số:

- Mọi đối tượng JSON mang đủ bốn trường `type`, `when`, `val` và `interp` được
  coi là một channel.
- Việc duyệt **đi sâu vào các channel lồng nhau**: `actions[].pose` (pose của
  Smart Bone) và `split[]` (các đường cong theo từng trục) là các channel riêng
  và được đếm riêng khỏi channel sở hữu chúng.

Điều đó cho **584,616 channel** và **604,139 mục `interp`** trên 19 file. Tổng
channel khớp với `moho-project-file-format.md` § 5, nên hai tài liệu đếm channel
theo cùng một cách. Tổng `interp` thì khác (tài liệu đó báo khoảng 210,000
mục), nên hãy coi các thống kê `interp` bên dưới là phép đo mới hơn.

Các khẳng định được dán nhãn:

- **Đã xác nhận (Confirmed)** — đọc trực tiếp từ các file, kèm số đếm.
- **Suy luận (Inference)** — cách đọc tốt nhất của bằng chứng, kèm bằng chứng.
- **Chưa giải mã (Not decoded)** — đã quan sát thấy, nhưng ý nghĩa chưa biết.
  Không đoán.

---

## 2. Ý tưởng cốt lõi: keyframe thưa thớt trên các channel độc lập

### 2.1 Một channel cho mỗi thuộc tính

Hầu như mọi thuộc tính trong Moho — vị trí một điểm, góc một bone, màu tô,
độ xoay một layer, thậm chí tên của child đang hiển thị của một switch layer —
được lưu dưới dạng cùng một đối tượng channel:

```jsonc
{
  "type": "Val",              // loại giá trị: Val, Vec2, Vec3, Color, Bool, String
  "when": [0, 25, 33, 41],    // thời điểm keyframe, tính theo frame
  "val":  [3.14, 3.20, 2.84, 3.20],
  "interp": [ {...}, {...}, {...}, {...} ]   // một mục cho mỗi keyframe
}
```

Không có danh sách frame ở cấp tài liệu và không có ảnh chụp toàn cảnh theo
từng frame. Một frame không hề được lưu; nó được **tính** bằng cách hỏi mọi
channel giá trị của nó tại thời điểm đó. Đây là điều làm file Moho nhỏ so với
độ dài của chúng, và là lý do `moho2svg.py` có thể xuất bất kỳ frame nào mà
không cần khái niệm "phát lại": xuất frame `N` nghĩa là đánh giá các channel
tại `N`.

### 2.2 Hầu hết channel không bao giờ chuyển động

**Đã xác nhận.** Trong 584,616 channel, có **571,915 channel có đúng một
keyframe** (97.8%) và chỉ **12,701 channel có hai keyframe trở lên** (2.2%).
Một channel một-keyframe là một hằng số; nó tồn tại chỉ vì Moho lưu mọi thuộc
tính theo cùng một hình dạng.

Số keyframe trên mỗi channel:

| Keyframe | Channel |
|---|---|
| 1 | 571,915 |
| 2 | 10,669 |
| 3 | 943 |
| 4 | 385 |
| 5–9 | 350 |
| 10–19 | 342 |
| 20+ | 12 |

Channel bận rộn nhất trong toàn bộ mẫu có 20 keyframe trở lên, và chỉ có 12
channel như vậy. Hoạt ảnh Moho thật được xây từ rất ít key.

### 2.3 Đánh số frame, và frame 0 nghĩa là gì

**Đã xác nhận.** Cả 19 tài liệu dùng `fps: 24.0`. Phạm vi được tạo là
`project_data.start_frame` … `end_frame`, và `start_frame` là **1** trong 18
tài liệu và **25** trong `Bandit.mohoproj`. Nó không bao giờ là 0.

Frame **0** là frame nghỉ / frame thiết lập, không phải frame đầu của hoạt ảnh:

- Các keyframe tại frame 0 giữ trạng thái trung tính của rig.
- `moho2svg.py` tính pose nghỉ của mọi bone chính xác tại **frame 0.0**
  (`Skinner.build`), và biến dạng của một mesh được định nghĩa tương đối với nó.
- `--frame` mặc định là `0`, nên đầu ra mặc định của công cụ là **pose nghỉ**,
  trong mọi tài liệu mẫu đều nằm ngoài phạm vi được tạo.

Thời điểm keyframe cũng có thể nằm **sau** `end_frame`, vì timeline của action
độc lập với timeline chính (xem [§ 7](#7-actions-và-smart-bones)):

| Tài liệu | Phạm vi được tạo | Thời điểm keyframe muộn nhất |
|---|---|---|
| `AddBone.animeproj` | 1–25 | 175 |
| `ControlBones.animeproj` | 1–120 | 240 |
| `WhatIsBone.animeproj` | 1–240 | 227 |
| `Bandit.mohoproj` | 25–127 | 87 |
| `ReparentBone.animeproj` | 1–120 | 0 (không có gì được hoạt ảnh) |

### 2.4 Thời gian keyframe âm tồn tại, và chúng không phải hoạt ảnh

**Đã xác nhận.** Giá trị `when` âm chỉ xuất hiện ở hai nơi:

- Các channel `timeline_markers`, luôn là giá trị đơn `-1000000`.
- Hai channel `transforms.translation` trong `SlickObjectTransition.mohoproj`,
  với các thời điểm như `-999916`, `-999971`, `-999970`, `-999919`.

**Suy luận:** `-1000000` là một sentinel nền ("xa trước timeline") thay vì một
thời điểm thật, và các key translation gần sentinel là tàn dư của cùng cơ chế
đó. Giá trị của chúng là giá trị mặc định của layer, nên bỏ qua chúng là vô
hại. Bản thân cơ chế **chưa được giải mã**.

Ảnh hưởng thực tế: một bộ đánh giá tuyến tính kẹp tại keyframe đầu sẽ trả
những giá trị tàn dư đó cho mọi frame trước key thật kế tiếp. Trong hai channel
đã quan sát, giá trị tàn dư bằng giá trị frame-0, nên không có gì sai nhìn thấy
được.

---

## 3. Giá trị giữa các keyframe được tạo ra thế nào

### 3.1 File lưu trữ gì

`when[i]`, `val[i]` và `interp[i]` **luôn cùng độ dài** (đã xác nhận trên mọi
channel, không ngoại lệ). `interp[i]` mô tả đoạn **rời khỏi** keyframe `i`, nên
mục cuối cùng không mô tả gì — trừ khi nó mang marker vòng lặp (xem
[§ 3.4](#34-v1--v2-và-marker-vòng-lặp)).

Mỗi mục `interp` có một hình dạng cố định:

```jsonc
{ "im": 1, "v1": 0.1, "v2": 0.5, "in": 1, "h": 0, "s": false, "t": 0,
  "b": [ {"ao": 0.000823, "ai": -0.00003, "po": 0.4375, "pi": 0.515625} ] }
```

`s` là `false` và `h` là `0` trên cả 604,139 mục. `in` là `1` ngoại trừ trên
2,052 mục, tất cả đều thuộc `fill_color`, `3d_thickness` hoặc `line_color`. Cả
hai đều **chưa được giải mã**.

### 3.2 `t` — loại nội suy

**Đã xác nhận** phân bố trên 604,139 mục:

| `t` | Số lượng | Xuất hiện ở đâu |
|---|---|---|
| `0` | 602,784 | khắp nơi; mặc định |
| `4` | 757 | `anim_pos`, `anim_scale`, `anim_angle`, pose của action |
| `2` | 540 | các trường tương tự |
| `256` | 33 | chỉ `physics_motor_speed` |
| `3` | 16 | chỉ `physics_motor_speed` |
| `1` | 4 | chỉ `physics_motor_speed` |
| `6` | 3 | chỉ `physics_motor_speed` |
| `5` | 2 | chỉ `physics_motor_speed` |

**Đã xác nhận và hữu ích:** mọi mục có `t` nằm ngoài `{0, 2, 4}` đều nằm trên
một channel **một keyframe**, nơi không có đoạn nào để nội suy. Trên các
channel thực sự chuyển động, chỉ quan sát thấy ba giá trị: `0` (mặc định),
`2`, và `4`.

**Chưa giải mã:** mỗi con số tên gọi chế độ nội suy nào của Moho. Không thể đọc
`t` như "4 = Bezier", vì `t == 4` xuất hiện trong ba bối cảnh khác nhau: với
tham số mặc định, với tay nắm Bezier tường minh, và với marker vòng lặp. Giá
trị trộn tự do trong một channel — một `anim_angle` chu kỳ đi bộ đơn lẻ trong
`Bandit.mohoproj` mang `t = [0, 4, 4, 2, 2, 2, 4, 4, 2, 2, 4]` — nên nó là một
lựa chọn theo từng keyframe do animator làm, không phải cài đặt toàn channel.

### 3.3 `im` — trường cờ, giải mã một phần

**Đã xác nhận** phân bố: `1` (446,672), `3` (151,877), `0` (3,803), `2`
(1,085), `5` (493), `9` (182), `7` (27).

Đó chính xác là các giá trị bạn có từ một trường 4-bit dùng các bit 1, 2, 4 và
8, và hai trong số các bit khớp với dữ liệu quan sát được:

| Bit | Bằng chứng | Cách đọc |
|---|---|---|
| `8` | `im == 9` trên **182** mục; mảng `b` hiện diện trên **đúng cùng 182 mục đó**, và không nơi nào khác | **Suy luận (mạnh):** bit 8 nghĩa là "tay nắm Bezier tường minh được lưu trong `b`" |
| `4` | các giá trị `im` `5` và `7` tổng cộng 520 mục; **471** trong số đó là mục **cuối** của channel chúng, và là các mục duy nhất mang các cặp `v1`/`v2` bất thường liệt kê bên dưới | **Suy luận:** bit 4 nghĩa là "keyframe này mang một cài đặt vòng lặp" |
| `1`, `2` | `im == 3` (bit 1+2) xuất hiện 151,877 lần, và 151,875 trong số đó nằm trên các channel một-keyframe | **Chưa giải mã** |

### 3.4 `v1` / `v2`, và marker vòng lặp

**Đã xác nhận.** Cặp `(0.1, 0.5)` xuất hiện trên **601,344 trong 604,139 mục** —
nó là mặc định không bị đụng tới và không mang thông tin. `(-1.0, -1.0)` xuất
hiện trên các channel mà animator thực sự đã làm việc.

Mọi thứ khác chỉ xuất hiện cùng với cờ bit-4 của `im`, trên keyframe cuối cùng
của một channel:

| `(v1, v2)` | Số lượng |
|---|---|
| `(-1.0, 2.0)` | 278 |
| `(15.0, -1000000.0)` | 140 |
| `(-1.0, 1.0)` | 47 |
| `(23.0, -1.0)` | 26 |
| `(15.0, -1.0)` | 2 |

**Suy luận, giờ đã giải mã đủ để dùng.** Đây là cài đặt *vòng lặp (cycle)* của
Moho: qua keyframe được đánh dấu, channel không giữ giá trị cuối của nó, nó
nhảy về và phát lại một đoạn sớm hơn trên chính timeline của nó. `v1` và `v2`
là cùng một cài đặt được nhập theo hai cách khác nhau, và chỉ một trong hai
được dùng tại một thời điểm — cái còn lại giữ một sentinel âm (`-1`, hoặc
`-1000000`):

| Slot | Khi được dùng | Ý nghĩa |
|---|---|---|
| `v1 >= 0` | animator nhập một số **tương đối** của frame | tiếp tục tại `when[i] - v1` |
| `v2 >= 0` | animator nhập một frame **tuyệt đối** | tiếp tục tại `v2` |

"Tiếp tục tại `R`" nghĩa là frame `end + 1` lấy giá trị của frame `R`, nên chu
kỳ lặp dài `end - R + 1` frame.

**Vòng lặp CỘNG DỒN — nó phát lại chuyển động, không phải các con số.** Mỗi
lần lặp cộng thêm `value(end) - value(R - 1)`, nên một chu kỳ đi bộ thật sự đi
được tới đâu đó thay vì đi tại chỗ. Delta đó bằng 0 với một vòng lặp liền
mạch, vốn là trường hợp phổ biến, và đó là lý do phân biệt này vô hình trên
hầu hết channel.

Đây là suy luận được kiểm chứng tốt nhất trong cả repo, vì nó là cái duy nhất
được đo đối chiếu với các frame do **chính Moho xuất ra**. Bone gốc `B1` của
`Bandit.mohoproj` mang `anim_pos` có key trên frame 25–41 với marker ở 41, và
x của nó tăng thêm `+0.710093` đơn vị tài liệu — 383.45 px — mỗi lần lặp 16
frame. Dự đoán vị trí nhân vật từ đó rồi so với 103 frame trong
`moho/Bandit/svg/`:

| Mô hình | \|sai số\| trung bình | \|sai số\| lớn nhất |
|---|---|---|
| **cộng dồn** | **3.3 px** | **8.4 px** |
| phát lại nguyên giá trị | 1025.7 px | 2299.4 px |

trên một quãng đi 2437 px. Phát lại nguyên giá trị khiến nhân vật đi tại chỗ;
bản đối chứng cho nó đi thẳng qua khung hình. Chỉ giá trị số và vector
`{x, y[, z]}` mới cộng dồn — màu, bool hay chuỗi không có khái niệm "lượng
thay đổi của một chu kỳ" nên được phát lại nguyên vẹn.

**Marker phải bị bỏ qua bên trong action pose của Smart Bone.** Moho cũng ghi
nó ở đó — `Bandit.mohoproj` mang đúng vòng lặp `(v1=15, end=41)` trên
`bones[0].anim_pos.actions[0].pose` y như trên chính channel — nhưng một action
là một thư viện tư thế do dial đánh chỉ số, không phải timeline chạy, và pose
được đọc như một *offset*, nên vòng lặp cộng dồn sẽ thêm một độ trôi không bao
giờ quay lại. Tôn trọng nó làm đầu và mõm của tài liệu đó lệch giả 590 px
suốt frame 44–80. Xem `Channel.without_cycles`.

**Cách điều này được kiểm tra.** Chỉ năm trong 19 tài liệu mẫu dùng vòng lặp,
và giữa chúng chỉ có bốn tổ hợp `(v1, v2, keyframe)` khác nhau. Với mỗi tổ
hợp, frame mà channel thực sự lặp về được tìm theo kinh nghiệm, bằng cách tìm
frame sớm hơn có giá trị **bằng** giá trị tại keyframe được đánh dấu — điều mà
một vòng lặp liền mạch làm cho đúng, và điều các animator dựng nên. Chấm điểm
trên mọi channel có vòng lặp của từng tài liệu, một ứng viên thắng rõ ràng:

| Tài liệu | `v1` | `v2` | keyframe được đánh dấu | frame thắng `A` |
|---|---|---|---|---|
| `Bandit.mohoproj` | 15 | -1000000 | 41 | 25 (92 trên 94 channel) |
| `TransformBoneTool.animeproj` | 23 | -1 | 25 | 1 (8 trên 10) |
| `WhatIsBone.animeproj` | -1 | 2 | 28 | 1 (212 trên 217) |
| `OffsetBoneTool.animeproj` | -1 | 2 | 24 | 1 (32 trên 32) |
| `BoneStrengthTool.animeproj` | -1 | 1 | 24 | 0 (quá ít channel số để phân biệt) |

Cả hai cách đọc đều rơi chính xác **muộn hơn một frame** so với người thắng đó
(`41 - 15 = 26` so với `A = 25`; `v2 = 2` so với `A = 1`), trong mọi tài liệu.
Độ lệch một frame đó chính là điểm mấu chốt: con số được lưu là frame mà channel
*tiếp tục tại*, không phải frame đầu của vòng lặp. Vì `value(A) == value(end)`
trên một vòng lặp liền mạch, phát lại `[A + 1, end]` và phát lại `[A, end]` cho
cùng một chuyển động, đó là lý do cả hai mô tả đều khớp — con số được lưu được
dùng trực tiếp.

Một kiểm tra thứ hai hỗ trợ điều đó: khi áp vòng lặp, bước giá trị qua chỗ
quấn lại (`end → end + 1`) không bao giờ là bước lớn nhất trong channel, trên
bất kỳ tài liệu nào trong bốn tài liệu. Một frame tiếp tục sai sẽ hiện ra ở đó
như một cú nhảy.

**Chưa xác nhận:** số lần lặp. Không có gì trong dữ liệu phân biệt "lặp vô
hạn" với "lặp N lần" — sentinel `-1000000` là một "vô hạn" hợp lý, nhưng `-1`
được dùng trong cùng slot ở nơi khác, nên cả hai đều được đọc ở đây đơn giản
là "slot này không được dùng". Vòng lặp do đó được xử lý như chạy vô hạn, hoặc
đến keyframe kế tiếp của channel khi marker không nằm trên key cuối (17 channel
trong `WhatIsBone.animeproj` như vậy: một vòng lặp trên frame 28 với một
keyframe nữa ở 227).

**Hệ quả cho bất kỳ công cụ nào bỏ qua `interp`:** một channel có vòng lặp
**không được** lặp. Qua keyframe được đánh dấu, giá trị bị kẹp thay vì lặp lại
— chu kỳ đi bộ của `Bandit.mohoproj` dừng ở frame 41 và của
`WhatIsBone.animeproj` dừng ở frame 28, cả hai đều ngắn hơn rất nhiều so với
frame cuối của chính tài liệu của chúng. `Channel` của `moho2svg.py` đọc marker
(xem `Channel._parse_cycles`), nên điều đó không còn áp dụng cho các exporter
của kho lưu trữ này.

### 3.5 `b` — tay nắm thời gian Bezier, đã giải mã

Mảng `b` hiện diện trên 182 mục. **Độ dài của nó bằng số thành phần trong giá
trị của channel** — đã xác nhận, không ngoại lệ:

| Loại channel `type` | `len(b)` | Mục |
|---|---|---|
| `Val` | 1 | 101 |
| `Vec3` | 3 | 38 |
| `Vec2` | 2 | 19 |
| `Bool` | 1 | 17 |
| `Color` | 1 | 5 |
| `String` | 1 | 2 |

Nên `b[c]` giữ đường cong thời gian của thành phần `c` — mỗi trục của một
`Vec2`/`Vec3` có tay nắm riêng. (`Color` nhận một mục duy nhất, không phải bốn.)

Mỗi mục là `{"ao", "ai", "po", "pi"}` — "ra" và "vào" của một cặp tay nắm:

- `po` / `pi` là **phân số thời gian của đoạn**, mặc định `0.333333` (một phần
  ba), là độ dài tay nắm Bezier kinh điển. Các giá trị quan sát được nằm trong
  `0 … 1`. **Suy luận, mạnh.**
- `ao` / `ai` là các thành phần **phía giá trị** tương ứng. Đọc chúng như một
  *tiếp tuyến* (đơn vị giá trị trên mỗi frame) được hỗ trợ bởi một tính chất
  chuỗi: trên 93 trong 153 cặp tay nắm liên tiếp, `interp[i].b[c].ai` bằng
  bit-for-bit với `interp[i+1].b[c].ao`, qua các đoạn có **độ dài khác nhau**.
  Các số bằng nhau qua các đoạn không bằng nhau khớp với một tốc độ, không phải
  một độ dời tuyệt đối. 60 cặp còn lại khác nhau, đó là điều một tay nắm bị cố
  ý phá (không trơn) sẽ trông như vậy. **Suy luận, trung bình.**

Đây là đường cong thời gian làm chuyển động của Moho vào-ra mềm mại. Chỉ một
số ít keyframe trong 19 tài liệu này dùng nó tường minh; mọi thứ khác dựa vào
đường cong mặc định (`t = 0`), hình dạng chính xác của nó **chưa được giải mã**.

### 3.6 Thay vào đó `moho2svg.py` làm gì

**Pose của Smart Bone được áp như một OFFSET, không phải thay thế** (được thêm
trong `Channel.eval` / `_pose_offset`). Một pose đóng góp
`pose(action_frame) - pose(first_action_keyframe)` lên trên giá trị timeline
chính của chính channel. Điều này chỉ hiện ra trên một channel được hoạt ảnh
trên timeline chính *và* được đăng ký trong một action, và `SketchBone.animeproj`
có đúng điều đó: dial `govde-don` của nó lưu một pose phẳng `[160.7, 160.7]`
trên bone `B16`, bằng góc nghỉ của bone đó, trong khi chính `B16` quét 126.3
-> 222.4 độ. Cách thay thế đóng băng cả cánh tay `kol-sag-ust` ở 160.7 độ cho
toàn bộ hoạt ảnh; cách offset làm một pose phẳng thành no-op mà nó rõ ràng là
vậy. Đã kiểm chứng với render chỉ phần cánh tay của chính Moho
(`moho/SketchBone/hand/`): mask IoU của cánh tay qua 120 frame là 11.5% ->
16.1%, khác biệt pixel toàn frame là -6.4%. Frame 0 không đổi (các dial nằm ở
trạng thái nghỉ, nên offset bằng không), nên các SVG xuất ra vẫn
byte-identical so với đầu ra trước thay đổi. Chỉ các channel số và vector
`{x,y,z}` bị offset; pose màu/bool/chuỗi vẫn thay thế.

`Channel.eval_raw` bỏ qua `interp` hoàn toàn và nội suy bằng **monotone cubic**
giữa hai keyframe bao quanh, kẹp ở cả hai đầu. (Một phiên bản trước nội suy
**tuyến tính**; điều đó không còn đúng nữa — xem `Channel._segment`.) Đường
cong easing của chính Moho không thể khôi phục từ file (`interp.t` là 0 trên
602,784 trong 604,139 mục với một enum chưa giải mã), nên hình dạng được suy
ra bằng cách chấm điểm đầu ra render so với render chỉ phần cánh tay của chính
Moho cho `SketchBone.animeproj` (`moho/SketchBone/hand/`, 120 frame):

| phép nội suy | IoU mọi frame | IoU frame 44–54 |
|---|---|---|
| tuyến tính | 84.55% | 60.88% |
| smoothstep ease | 79.50% | 65.67% |
| Catmull-Rom | 82.20% | 78.59% |
| **monotone cubic** | **85.76%** | **81.84%** |

Frame 44–54 là cửa sổ phân biệt: chúng nằm *giữa* các keyframe cánh tay của rig
đó (43, 49, 55), nơi phép tuyến tính đạt ~89% **tại** mỗi keyframe nhưng sụp
xuống 45–65% giữa chúng — pose đúng, đường cong sai. Trên toàn bộ hoạt ảnh,
điều này cắt khác biệt pixel toàn frame đi **43.3%**. Nó vẫn là một đường cong
được suy ra, không phải được giải mã. Frame 0 không bị đụng tới, nên các SVG xuất ra
vẫn byte-identical so với trước thay đổi.

- số → nội suy monotone-cubic;
- `{x,y}`, `{x,y,z}`, `{r,g,b,a}` → tuyến tính theo từng thành phần;
- chuỗi và boolean → bám vào keyframe bên trái (không nội suy), là lựa chọn
  đúng duy nhất cho tên của switch-layer hay cờ hiển thị.

Hệ quả, theo thứ tự quan trọng thực tế:

1. **Chính xác tại mọi keyframe.** Bất kỳ frame nào là keyframe của mọi channel
   liên quan đều được tái tạo chính xác, trừ các tính năng rig trong
   [§ 6](#6-chuyển-động-không-nằm-trong-keyframe).
2. **Xấp xỉ giữa các keyframe.** Chuyển động tuyến tính thay vì chuyển động
   eased. Kích thước nhìn thấy được của sai số phụ thuộc vào đoạn, và lớn nhất
   trên các đoạn dài với easing mạnh.
3. **Vòng lặp được áp dụng**, từ marker đã giải mã trong
   [§ 3.4](#34-v1--v2-và-marker-vòng-lặp). Số *lần* lặp vẫn chưa được giải mã,
   nên một vòng lặp chạy đến keyframe kế tiếp của channel, hoặc vô hạn khi
   marker nằm trên key cuối.
4. **`split` bị bỏ qua** — các mảng `Vec2`/`Vec3` cha được đọc thay thế. Chỉ
   một channel trong toàn bộ mẫu dùng `split` (một `anim_pos` trong
   `Bandit.mohoproj`), và đường cong split của nó khớp với cha, nên hiện tại
   không có gì sai.

Để đặt một con số cho điểm 2: đánh giá lại 63 đoạn `Val` mang tay nắm tường
minh, theo cách đọc tiếp tuyến của `ao`/`ai` từ
[§ 3.5](#35-b--tay-nắm-thời-gian-bezier-đã-giải-mã), khoảng cách lớn nhất giữa
đường cong eased và đường thẳng là khoảng **0.14 rad (8°)** giữa đoạn — trên
pose `anim_angle` của bone `TorsoA` trong action `Jump` của `Rabbit.animeproj`,
mà hai key của nó chỉ cách nhau 0.22 rad. Con số đó thừa hưởng độ bất định của
cách đọc tiếp tuyến, nên hãy coi nó như một bậc độ lớn: **sai số giữa đoạn có
thể là một phần lớn của mức thay đổi từ key này sang key kia, trong khi các
keyframe vẫn chính xác**.

---

## 4. Chuyển động thực sự nằm ở đâu

Đây là phần giải thích vì sao file Moho trông như chúng trông. Đếm **chỉ các
channel nhiều keyframe** — tức các thuộc tính một animator thực sự đã động
vào — trên cả 19 tài liệu:

| Trường | Channel nhiều key | Nó hoạt ảnh cái gì |
|---|---|---|
| `actions[].pose` | 11,816 | một đường cong pose được lưu (Smart Bones và actions) |
| `anim_angle` | 383 | xoay bone |
| `position` | 159 | một điểm mesh di chuyển trực tiếp |
| `anim_scale` | 151 | tỷ lệ bone |
| `anim_pos` | 146 | vị trí bone |
| `bone_dynamics` | 14 | physics bật/tắt theo thời gian |
| `translation` | 8 | vị trí riêng của một layer |
| `scale` | 4 | tỷ lệ riêng của một layer |
| `offset_in` / `offset_out` | 8 | hình dạng tay nắm Bezier của một curve point |
| `layer_effects.visibility` | 4 | hiện/ẩn được hoạt ảnh |
| `rotation_z` | 3 | độ xoay riêng của một layer |
| `flip_h` | 2 | lật ngang |
| `switch_keys` | 2 | child nào của switch-layer đang hiển thị |

Đọc bảng đó như bản tóm tắt thiết kế của Moho: **chuyển động được lưu trên
rig, không phải trên bản vẽ**. Hoạt ảnh điểm trực tiếp (159 channel) hiếm;
hoạt ảnh transform của layer (15 channel) còn hiếm hơn; các channel bone và
pose được lưu chiếm gần như tất cả.

Theo từng tài liệu, nguồn chuyển động dễ nhận diện:

| Tài liệu | Nguồn chuyển động chính |
|---|---|
| `Bandit.mohoproj` | bones (`anim_pos`/`anim_angle`/`anim_scale`, mỗi loại 25) cộng một action `Walk` |
| `WhatIsBone.animeproj` | bones (214 `anim_angle` được hoạt ảnh) cộng poses và một switch layer |
| `SketchBone.animeproj` | bones cộng poses, một switch layer (miệng), và `flip_h` |
| `OffsetBoneTool.animeproj` | hoạt ảnh điểm trực tiếp (132 channel `position`) cộng bones |
| `SlickObjectTransition.mohoproj` | **chỉ transform của layer** — không hề có skeleton |
| `AddBone`, `TargetBone`, `IK-FK`, `ControlBones`, … | chỉ pose được lưu |
| `ReparentBone`, `SelectandReparentBoneTool` | không có gì được hoạt ảnh (demo rig) |

`SlickObjectTransition.mohoproj` là phản ví dụ hữu ích: một tài liệu hoạt ảnh
`translation`, `scale`, `rotation_z`, `visibility` và cả tay nắm curve-point
(`offset_in`/`offset_out`) mà không có bone ở đâu cả.

---

## 5. Ngăn xếp transform

Một điểm được vẽ đi qua nhiều không gian trước khi đáp xuống canvas. Thứ tự là
cố định, và làm sai nó là cách kinh điển để tạo ra đầu ra trông *gần như* đúng.

### 5.1 Ma trận của riêng một layer

`transforms` giữ mười channel; năm trong số đó định nghĩa ma trận 2D:
`translation` (`Vec3`), `scale` (`Vec3`), `rotation_z` (`Val`), `flip_h` và
`flip_v` (`Bool`). Xoay và tỷ lệ xoay quanh `origin` của layer — một điểm
thường (không hoạt ảnh) — không phải quanh `(0, 0)` cục bộ:

```
p' = origin + translation + R(rotation_z) · S(scale_x, scale_y) · (p - origin)
```

`flip_h` / `flip_v` đảo dấu `scale_x` / `scale_y`. Tỷ lệ của layer thực sự là
**theo từng trục**; tỷ lệ của một bone là một vô hướng duy nhất (xem § 5.3).

Các channel transform còn lại — `rotation_x`, `rotation_y`, `shear`,
`following`, `physics_nudge`, và các thành phần `z` — **không được dùng** bởi
`moho2svg.py`. Tất cả đều ở giá trị mặc định trong các mẫu trừ các thành phần
`z`, nên không có gì quan sát được đang sai.

### 5.2 Chuỗi transform, và vì sao skinning không chỉ là một ma trận khác

Các ma trận của chuỗi tổ tiên hợp theo cách thông thường, **nhưng biến dạng
bone không phải một ma trận và không giao hoán với chúng**. Skinning xảy ra
trong không gian tọa độ *riêng* của bone layer:

```
điểm mesh thô (không gian riêng của mesh layer)
      |  mọi ma trận cục bộ giữa mesh và bone layer, hợp lại
      v
không gian riêng của BoneLayer          <- các ma trận của skeleton sống ở đây
      |  skinning (cứng hoặc mềm)
      v
vẫn là không gian riêng của BoneLayer, giờ đã pose
      |  ma trận cục bộ của chính bone layer, rồi mọi thứ phía trên nó
      v
không gian tài liệu
      |  2 đơn vị trải dài chiều cao canvas, y bị lật
      v
không gian pixel
```

Nên một mesh lồng sâu vài nhóm bên trong một `BoneLayer` bị biến dạng *sau*
các transform cục bộ giữa nó và bone layer, và *trước* transform của chính
bone layer. `build_deform_chain` trong `moho2svg.py` tạo ra chính xác danh sách
các bước có thứ tự này; `moho-export-pipeline.md` § 4.2 có chi tiết cài đặt.

Một bất nhất cố ý đáng biết: **độ rộng nét dùng một phép duyệt khác** hợp mọi
ma trận layer nhưng **loại trừ biến dạng bone**. Đó không phải sơ suất — gộp
biến dạng bone vào làm độ rộng nét phình thêm khoảng 11% trong một bài kiểm
chu kỳ đi bộ.

### 5.3 Transform của bone

Mỗi bone mang `anim_pos` (`Vec2`, tương đối với bone cha), `anim_angle`
(`Val`, radian) và `anim_scale` (`Val`, một vô hướng duy nhất). Ma trận world
của một bone là ma trận world của cha nhân ma trận cục bộ của chính nó, với
các bone cha được giải trước các bone con bất kể thứ tự danh sách — mảng
`bones` không đảm bảo được sắp xếp topo.

Ma trận cục bộ khi cài đặt chỉ tỷ lệ cột đầu tiên:

```
local = Mat2D(cos·scale, sin·scale, -sin·across, cos·across, pos.x, pos.y)
```

`across` là `1` cho một bone có `scaling_mode == 2` (chỉ tỷ lệ dọc theo bone)
và bằng `scale` cho mọi bone khác (tỷ lệ đều thông thường).

**`scaling_mode` giờ đã được giải mã**, sửa một phiên bản trước vốn gọi sự bất
đối xứng là chưa giải thích được và cảnh báo không nên đụng vào. Nó là công tắc
**"Squash and stretch scaling"** theo từng bone của Moho, và chỉ tỷ lệ một trục
chính là điều squash-and-stretch nghĩa là gì. Bằng chứng là rig đầu `kafasi`
của `SketchBone.animeproj`: hai bone mang mỗi tai (`B2`/`B3` và `B4`/`B5`) có
`scaling_mode == 2`, trong khi bone thứ ba trong `flexi_bone_subset` của chính
mỗi tai (`B20`, `B19`) có `0` — đúng sự phân chia mà bảng bone constraints của
Moho hiển thị cho rig đó. Trên toàn bộ mẫu: `2` trên 264 bone, `0` trên 586.

Chỉ 28 bone trong toàn bộ mẫu từng đưa `anim_scale` ra khỏi `1.0`, và 9 trong
số đó là `scaling_mode == 0` (trong `Rabbit`, `BoneDynamics`, `BoneStrengthTool`
và `OffsetBoneTool`), nên đó là những nơi duy nhất sự đính chính có thể quan
sát được. Không tài liệu nào trong số chúng xuất hiện trong các tài liệu mẫu có đầu ra
được kiểm byte-identical, đó là lý do các SVG xuất ra không đổi.

### 5.4 Bind cứng (rigid) và bind mềm (flexible)

Việc bind được quyết định **theo từng layer** bởi `parent_bone`:

- `parent_bone >= 0` — **cứng**: mọi điểm đi theo đúng bone đó.
- `parent_bone == -1` — **mềm / region**: mọi điểm là một blend có trọng số
  theo khoảng cách của tất cả các bone, hoặc của tập con được đặt tên bởi
  `flexi_bone_subset` (một danh sách các **chỉ số** bone nối bằng `"|"`, dạng
  chuỗi).

Một giá trị thứ ba, `parent_bone == -3`, xuất hiện trên 9 `ImageLayer` và chưa
được giải mã.

Pose nghỉ được đánh giá tại frame 0.0, và mỗi bone đóng góp `pose · rest⁻¹`.
Một bone có `strength <= 0` bị bỏ qua hoàn toàn trước bất kỳ phép tính trọng
số nào — đó là cổng "bone này không biến dạng mesh này" của Moho (241 trong
850 bone). Hình dạng suy giảm dùng cho blend (nghịch đảo bình phương khoảng
cách) là một **heuristic** mà không có tham chiếu sẵn có nào xác nhận được so
với các lựa chọn thay thế.

Phép toán skinning từng bước, tham chiếu đầy đủ các trường bone, và chi phí
theo từng tính năng của việc bỏ qua constraints/IK/control bones nằm trong
[`moho-rigging-and-deformation.md` § 2](moho-rigging-and-deformation.md#2-hệ-thống-bone).

---

## 6. Chuyển động không nằm trong keyframe

Đây là khoảng trống lớn nhất giữa "file nói" và "Moho hiển thị", và là phần dễ
bỏ sót nhất: một số tính năng rig **tạo ra chuyển động lúc render** mà không
ghi bất kỳ keyframe nào. Không có gì bake chúng vào `anim_angle`.

**Đã xác nhận bằng cách kiểm tra trực tiếp các trường của cả 850 bone:**

| Tính năng | Các trường | Nơi nó được bật |
|---|---|---|
| Bone dynamics (physics lò xo) | `bone_dynamics` (channel `Bool`), `spring_force`, `damping_force`, `torque_force` | **115 bone trong 6 tài liệu**: `WhatIsBone` (52), `Bandit` (28 — mọi bone), `AddBone` (21), `BoneDynamics` (6), `Rabbit` (6), `ControlBones` (2) |
| Angle dynamics | `angle_dynamics` | 2 bone trong `Bandit.mohoproj` |
| Ràng buộc góc | `constraints`, `min_constraint`, `max_constraint` | **158 bone trong 11 tài liệu** |
| Control bones | `angle_control_parent`, `pos_control_parent`, `scale_control_parent` (+ `_scale`, `_delay`) | 4 tài liệu: `ControlBones` (mỗi loại 2 bone cho angle/pos/scale), `BoneDynamics`, `AddBone`, `Rabbit`. `Bandit` chỉ đặt `scale_control_delay` (8, trên một bone) |
| Mục tiêu IK | `target_bone`, `ik_lock`, `ik_global_angle`, `ignored_by_ik` | `target_bone` được đặt trên 41 bone trong 14 tài liệu (1–8 bone mỗi tài liệu) |
| Đổi cha theo thời gian | `anim_parent` | không bao giờ được keyframe ở đây — xem bên dưới |

> **Đính chính.** `moho-project-file-format.md` § 9 nói rằng các trường
> physics/dynamics "đều bị tắt trong các mẫu". Điều đó không đúng: `bone_dynamics`
> là một channel `Bool` có giá trị `true` trên 115 bone, và `BoneDynamics.animeproj`
> thậm chí còn keyframe nó (7 channel có nhiều hơn một key). Gạch đầu dòng § 9
> đã được sửa cho khớp.

Vì sao điều này quan trọng với bất kỳ công cụ xuất nào: `Bandit.mohoproj` bật
dynamics trên cả 28 bone của nó — 22 trong số đó với `spring_force: 2.0`,
`damping_force: 1.0`, `torque_force: 2.0`, và 6 cái được chỉnh riêng — trong
khi các channel `anim_angle` của nó chỉ giữ các key của riêng animator. Trong
Moho, chuyển động theo đà (follow-through) đàn hồi được cộng lên trên các key
đó lúc phát lại. Một công cụ chỉ đánh giá channel — như `moho2svg.py` — render
pose đã key **không có** chuyển động phụ. Nên đây là một khoảng trống **đã
được vận hành**, không phải lý thuyết: ảnh tĩnh thiếu overlap và follow-through
mà Moho sẽ hiển thị, và khoảng trống lớn dần theo khoảng cách tới một keyframe.

Hai tính năng trong bảng an toàn để bỏ qua, và điều này được đo chứ không phải
giả định:

- **`anim_parent`** (đổi cha của bone theo thời gian): cả 850 channel có đúng
  một keyframe, và giá trị đó bằng `parent` tĩnh của bone trong 850/850 trường
  hợp. Ngay cả `ReparentBone.animeproj` cũng chỉ trình diễn *công cụ* mà không
  bao giờ keyframe một lần đổi cha.
- **Constraints**: chúng giới hạn những gì animator có thể pose trong editor;
  góc kết quả đã được lưu trong `anim_angle`.

Mỗi tính năng trong số này được bao phủ theo từng trường, kèm chi phí bỏ qua
nó, trong
[`moho-rigging-and-deformation.md` § 3](moho-rigging-and-deformation.md#3-ràng-buộc-bone-và-công-cụ-hỗ-trợ-rig).
Hai trường rig không được liệt kê trong bảng trên cũng hóa ra là không mặc
định ở đâu đó trong mẫu: `bone.offset` (5 bone, công cụ Offset Bone) và
`skeleton.binding_mode` (`2` trên một skeleton). Cả hai đều chưa được giải mã.

---

## 7. Actions và Smart Bones

Actions là cách Moho tái dùng chuyển động. Chúng sống ở hai nơi khác nhau trông
giống nhau.

### 7.1 Sổ đăng ký tên

Gần như mọi layer mang `actions: [{"name": "...", "pose": 0}]` — 19,921 mục
trong mẫu, với `pose` luôn là số nguyên `0`. Đây là một **sổ đăng ký tên action
cấp tài liệu, nhân bản trên gần như mọi layer**, không phải danh sách theo
layer. Bằng chứng: một `BoneLayer` với **không bone** trong `WhatIsBone.animeproj`
mang cùng 37 tên action như layer 157-bone phía trên nó.

### 7.2 Các đường cong pose

Dữ liệu thật nằm trên các channel riêng lẻ. Bất kỳ channel nào cũng có thể
mang danh sách `actions` riêng, và ở đó `pose` là một **channel lồng hoàn
chỉnh** với `when`/`val`/`interp` riêng:

```jsonc
"actions": [
  { "name": "EyeBlink",
    "pose": { "type": "Vec2", "when": [0, 6, 12], "val": [...], "interp": [...] } }
]
```

Có 11,816 pose như vậy — thứ được keyframe nhiều nhất trong các tài liệu này,
vượt xa 383 channel `anim_angle`. **Cả 11,816 pose đều có hai keyframe trở
lên**, không ngoại lệ, đây chính là thứ mà phép đảo dial trong
[§ 7.3](#73-dial-so-với-action-thường) cần: một đường cong một điểm không thể
đảo. Loại channel của pose là
`Vec2` (10,024), `Val` (1,561), `Vec3` (165), `Color` (37), `Bool` (22) và
`String` (7): một action có thể ghi đè bất kỳ thuộc tính nào, kể cả màu.

Timeline của một action là **của riêng nó**, đó là lý do thời điểm keyframe có
thể vượt quá `end_frame` của tài liệu ([§ 2.3](#23-đánh-số-frame-và-frame-0-nghĩa-là-gì)).

### 7.3 Dial so với action thường

Một tên action được đăng ký trở thành **Smart Bone dial** khi nó khớp với
`name` của một bone trong skeleton của `BoneLayer` bao quanh. Các tên không
khớp bone nào là **action thường**: các clip dùng lại mà người dùng kích hoạt
từ cửa sổ Actions của Moho. Không có gì trong file nói một action thường đang
chạy, nên một trình render phải để nó tắt — `"Walk"` của `Bandit.mohoproj`
chính là trường hợp này.

Khi dial `D` đang hoạt động, một channel mang một mục tên `D` đọc từ pose đó
thay vì các key riêng, tại một frame tìm được bằng cách **đảo đường cong
pose**: mảng `val` của pose ghi lại góc của chính dial tại mỗi keyframe của
pose, nên "frame của pose mà góc ghi lại bằng góc hiện tại của dial" được định
nghĩa rõ. Vì một đường cong phải gần như đơn điệu mới đảo được, Moho lưu hai
action cho mỗi dial, một cho mỗi hướng xoay, action thứ hai có hậu tố `" 2"`
(`"BlinkL"` và `"BlinkL 2"`).

Việc phân giải góc hiện tại của chính dial **không được** đi qua cỗ máy ghi
đè mà dial là một phần của nó; nó đọc channel thô.

---

## 8. Switch layer: hoạt ảnh rời rạc

Một `SwitchLayer` hiển thị đúng một child tại một thời điểm, và child nào được
hoạt ảnh bởi `switch_keys` — một channel `String` có giá trị là **tên các
child layer**. Vì chuỗi bám vào keyframe bên trái, đây là một hàm bậc thang,
đúng thứ cần cho các hình miệng.

**Đã xác nhận**, cả hai trường hợp được hoạt ảnh trong mẫu:

- `SketchBone.animeproj`: `when = [0, 74, 76, 78, 80, 82, 84, 86]`,
  `val = ["agiz", "agiz", "agiz 2", "agiz 3", "agiz 4", "agiz 5", "agiz 6",
  "agiz"]` — một cái miệng lặp qua sáu hình trên mỗi frame cách một, tức lip
  sync.
- `WhatIsBone.animeproj`: `when = [0, 1]`, `val = ["agiz1", "agiz6"]`.

`moho2svg.py` cài đặt điều này (`Layer.switch_active_child`), kể cả một fallback
mà chính Moho dùng: nếu tên được ghi không khớp child nào — xảy ra khi một
child được đổi tên sau khi key được đặt — thì child **đầu tiên** được vẽ thay
vì không vẽ gì.

---

## 9. Hoạt ảnh camera

`doc.animated_values` giữ năm channel: `camera_track` (`Vec3`),
`camera_pan_tilt` (`Vec2`), `camera_zoom` (`Val`), `camera_roll` (`Val`) và
`timeline_markers` (`String`). Tất cả đều có đúng một keyframe tại frame 0
trong cả 19 tài liệu, nên không mẫu nào hoạt ảnh camera.

`moho2svg.py` không đọc channel nào trong số chúng và render với một camera cố
định ngầm. `Rabbit.animeproj` có một `camera_track` và `camera_zoom` thực sự
không mặc định, nên khung hình trong tài liệu đó không đảm bảo khớp với Moho.

---

## 10. Render hoạt ảnh bằng `moho2svg.py`

Công cụ xuất **một frame mỗi lần chạy**. Không có chế độ chuỗi tích hợp.

```bash
# Một frame (frame 0 = pose nghỉ, nằm trước phạm vi được tạo)
python3 moho2svg.py moho/Bandit.mohoproj --combined out/frame_0025.svg --frame 25

# Một dải nguyên, một SVG mỗi frame
for f in $(seq 25 127); do
  python3 moho2svg.py moho/Bandit.mohoproj \
      --combined "out/frame_$(printf '%04d' "$f").svg" --frame "$f"
done
```

Các ghi chú đến từ việc thực sự chạy điều này:

- **Đầu ra là xác định** cho một frame: xuất cùng frame hai lần cho các file
  byte-identical (đã kiểm chứng trên `Bandit.mohoproj` frame 41).
- **Các frame khác nhau như dự kiến**: frames 0, 25, 33 và 41 của
  `Bandit.mohoproj` mỗi cái tạo ra hình học khác nhau.
- **Việc kẹp là theo channel, không theo tài liệu.** Frame 200 nằm sau key bone
  cuối (41) nhưng không sau mọi channel trong file (key muộn nhất là 87), nên
  nó không giống hệt frame 41. Chỉ một frame sau key cuối của *mọi* channel mới
  là một đóng băng thật.
- **`--frame` nhận một số nguyên.** Bản thân bộ đánh giá làm việc bằng số chấm
  động, nên việc lấy mẫu dưới frame là có thể trong code nhưng không từ dòng
  lệnh.
- Thêm `--brush-dir ""` trong khi lặp: việc stamp brush chiếm ưu thế thời gian
  xuất, và tắt nó làm một vòng lặp theo frame khả thi.
- Dùng **cùng các cờ cho mọi frame**. Đổi `--crop` giữa các frame thay đổi
  viewBox và chuỗi sẽ bị giật.

---

## 11. Tóm tắt các khoảng trống về hoạt ảnh và transform

Sắp theo khả năng nó làm thay đổi những gì bạn thấy.

| Khoảng trống | Trạng thái | Ảnh hưởng |
|---|---|---|
| Bone dynamics (lò xo) bị bỏ qua | **đã vận hành** — 115 bone trong 6 tài liệu | thiếu follow-through / overlap; tệ nhất khi xa keyframe |
| Easing (`interp`) bị bỏ qua, dùng tuyến tính | **đã vận hành** — mọi channel nhiều key | chính xác tại keyframe, xấp xỉ giữa chúng |
| Cài đặt vòng lặp bị bỏ qua | **đã vận hành** — ~470 channel mang marker trên key cuối | chuyển động dừng ở key cuối thay vì lặp |
| `layer_effects.visibility` bị bỏ qua | **đã vận hành** — 4 channel hoạt ảnh trong `SlickObjectTransition` | một layer lẽ ra xuất hiện/biến mất giữa hoạt ảnh thì không |
| Control bones (`*_control_parent`) bị bỏ qua | **đã vận hành** — một số ít bone trong 4 tài liệu | các bone bị điều khiển không theo driver của chúng |
| IK (`target_bone`) bị bỏ qua | vận hành một phần | pose được giải thường đã nằm trong `anim_angle`; một chi điều khiển bằng target có thể không |
| Các channel camera bị bỏ qua | không vận hành (tất cả tĩnh) | khung hình sẽ sai trong một tài liệu có camera di chuyển |
| Các đường cong theo trục `split` bị bỏ qua | không vận hành (1 channel, giá trị khớp) | giá trị sai nếu các trục được key khác nhau |
| Channel `mute: true` vẫn được hoạt ảnh | không vận hành (channel mute duy nhất có một key) | một channel nhiều key bị mute sẽ chuyển động khi Moho đóng băng nó |
| `anim_parent` (đổi cha) bị bỏ qua | **không vận hành** — 850/850 khớp cha tĩnh | không có, với các file này |

---

## 12. Tái tạo lại các con số

Mọi số đếm trong tài liệu này đến từ việc duyệt JSON thô của 19 file trong
`moho/`, với các quy tắc này:

1. Một dict giữ tất cả `type`, `when`, `val`, `interp` là một channel.
2. Đi sâu vào `actions[].pose` và `split[]` và đếm chúng như các channel riêng.
3. "Được hoạt ảnh" nghĩa là `len(when) > 1`.
4. Với các cờ bone được lưu như channel (`bone_dynamics`, `target_bone`, …),
   lấy `val[0]` và so với mặc định của trường.

Quy tắc 2 là thứ thay đổi kết quả nhiều nhất: bỏ qua các pose lồng nhau giấu
11,816 trong 12,701 channel được hoạt ảnh — tức giấu hầu hết hoạt ảnh trong
một tài liệu Moho có rig.
