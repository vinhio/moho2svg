# Rigging và Biến dạng của Moho

> Bản dịch tiếng Việt của `docs/moho-rigging-and-deformation.md`. Bản tiếng Anh là nguồn tham chiếu chính thức.

Bones, Smart Warp, và các trường cấp mesh ràng buộc cách artwork bị biến dạng.

Moho có ba cách khác nhau để uốn artwork, và chúng dễ bị nhầm lẫn:

1. **Bones** — một skeleton làm biến dạng các điểm của một mesh (hoặc dời cả
   layer theo kiểu cứng, rigid). Đây là hệ thống rigging chính, và cũng là hệ
   thống duy nhất `moho2svg.py` cài đặt.
2. **Smart Warp** — một mesh biến dạng riêng đặt lên trên một layer hoặc một
   nhóm. Không file nào trong bộ mẫu dùng nó, nên tài liệu này chỉ có thể mô tả
   các móc (hooks) mà định dạng để lại cho nó.
3. **Các trường cấp mesh** — các cài đặt theo điểm, theo curve và theo layer
   giới hạn hoặc định hình lại hai thứ kia (bone subsets, nhóm điểm, curve
   profiles, cắt tỉa curve, cờ deformer).

Các tài liệu đồng hành:

- [`moho-project-file-format.md`](moho-project-file-format.md) — tham chiếu
  đầy đủ các trường. § 9 là bản ngắn về bones; tài liệu này là bản dài.
- [`moho-animation-and-transform.md`](moho-animation-and-transform.md) — cách
  các channel lưu chuyển động, và cách ngăn xếp transform hợp lại.
- [`moho-export-pipeline.md`](moho-export-pipeline.md) — cách `moho2svg.py`
  duyệt một tài liệu và sinh ra SVG.

Tài liệu này không lặp lại những tài liệu đó. Nó đi sâu hơn vào bản thân rig,
và nói rõ phần nào được đọc từ các file thật và phần nào không.

---

## 1. Phạm vi và cơ sở bằng chứng

Mọi số đếm ở đây được đo từ 19 file dự án trong thư mục (bị gitignore) `moho/`:
17 `.animeproj` và 2 `.mohoproj`, thuộc ba thế hệ định dạng — `1021` (1 file),
`1038` (17 file) và `1045` (1 file).

Mẫu chứa:

| Mục | Số lượng |
|---|---|
| Layer mọi loại (cây `layers`) | 842 |
| `BoneLayer` | 47 |
| đối tượng `skeleton` (trên `BoneLayer` **và** `SwitchLayer`) | 64 |
| đối tượng `skeleton` có danh sách `bones` không rỗng | 42 |
| Bone | 850 |
| Bone trên mỗi skeleton | 1 – 157 |

Mọi số đếm layer trong tài liệu này chỉ duyệt cây `layers`, nên dừng ở 842.
`moho-project-file-format.md` § 6.2 đôi khi báo 876 thay vào đó, vì nó cũng
đếm `MeshLayer` lồng bên trong mỗi `TextLayer` trong số 34 cái. Cả hai đều
đúng; hãy kiểm tra quần thể nào một con số đang nói tới trước khi so hai tài
liệu.

22 skeleton có danh sách `bones` rỗng là 17 skeleton của `SwitchLayer` cộng 5
skeleton của `BoneLayer`. Một `SwitchLayer` luôn mang một đối tượng `skeleton`;
nó rỗng trong mọi mẫu, nên đừng coi "có khóa `skeleton`" là "là một bone layer".

Các khẳng định được dán nhãn giống tài liệu hoạt ảnh:

- **Đã xác nhận (Confirmed)** — đọc trực tiếp từ các file, kèm số đếm.
- **Suy luận (Inference)** — cách đọc tốt nhất của bằng chứng, kèm bằng chứng.
- **Chưa giải mã (Not decoded)** — đã quan sát thấy, nhưng ý nghĩa chưa biết.
  Không đoán.
- **Không có trong mẫu (Not in the sample)** — tính năng tồn tại trong Moho,
  nhưng không file nào ở đây dùng nó, nên không có gì về cách lưu trữ của nó
  được ghi lại.

Phần [9](#9-tái-tạo-lại-các-con-số) chỉ cách tính lại các con số.

---

## 2. Hệ thống bone

### 2.1 Skeleton sống ở đâu

Một skeleton thuộc về một `BoneLayer`:

```
BoneLayer
  skeleton: { type, binding_mode, bones: [ ... ], bones_groups? }
  layers:   [ các layer mà skeleton này có thể biến dạng ]
```

Các bone biến dạng các layer **lồng bên trong** `BoneLayer` đó. Một layer bên
ngoài nó không bao giờ bị skeleton đó đụng tới. Việc lồng có thể sâu: một mesh
vài nhóm dưới bone layer vẫn bị biến dạng, và nó bị biến dạng trong *không
gian tọa độ riêng của bone layer* — sau các ma trận cục bộ giữa mesh và bone
layer, và trước ma trận riêng của bone layer. Xem
[`moho-animation-and-transform.md` § 5.2](moho-animation-and-transform.md#52-chuỗi-transform-và-vì-sao-skinning-không-chỉ-là-một-ma-trận-khác).

`bones` là một **danh sách phẳng**, không phải cây. `bone.parent` là một chỉ
số vào chính danh sách đó, hoặc `-1` cho bone gốc. Các bone cha **không** được
đảm bảo xuất hiện trước các bone con, nên bất kỳ code nào tính ma trận world
phải phân giải chuỗi cha của từng bone theo nhu cầu thay vì duyệt danh sách
theo thứ tự (`Skeleton.world_matrices` trong `moho2svg.py` làm điều này, ghi
nhớ các bone đã thăm).

### 2.2 Bản ghi bone

Tất cả 40+ trường bone, nhóm theo mục đích. "Được dùng" nghĩa là `moho2svg.py`
đọc nó khi render.

**Hình dạng và danh tính (được dùng)**

| Trường | Loại | Ý nghĩa |
|---|---|---|
| `name` | str | Tên bone. Cũng là khóa khớp một Smart Bone dial với một action ([§ 4](#4-smart-bones-trong-một-trang)). |
| `parent` | int | Chỉ số vào cùng danh sách `bones`, `-1` cho bone gốc. |
| `length` | float | Độ dài bone tính theo đơn vị tài liệu. Quan sát `0.003117` – `0.981441`. |
| `strength` | float | Bán kính ảnh hưởng cho bind mềm. Quan sát `0.0` – `7.654676`; **`0.0` trên 241 trong 850 bone**, nghĩa là "bone này không biến dạng mesh chút nào". |

**Pose (được dùng)**

| Trường | Loại | Ý nghĩa |
|---|---|---|
| `anim_pos` | channel `Vec2` | Vị trí tương đối với bone cha. |
| `anim_angle` | channel `Val` | Góc tính bằng radian. Channel bone được keyframe nhiều nhất: 383 trong 850 bone có nhiều hơn một key. |
| `anim_scale` | channel `Val` | Một tỷ lệ vô hướng duy nhất dọc theo bone. Chú ý đây là **một con số**, không như tỷ lệ theo trục của một layer. Giá trị đầu là `1.0` trên cả 850 bone. |

**Constraints và công cụ hỗ trợ rig (không dùng — [§ 3](#3-ràng-buộc-bone-và-công-cụ-hỗ-trợ-rig))**

`constraints`, `min_constraint`, `max_constraint`, `fixed_angle`,
`angle_control_parent` / `_scale` / `_delay`, `pos_control_parent` / `_scale`
/ `_delay`, `scale_control_parent` / `_scale` / `_delay`, `target_bone`,
`ik_lock`, `ik_global_angle`, `ik_parent_target`, `ignored_by_ik`,
`bone_enable_arc_solver`, `anim_parent`.

**Hành vi tỷ lệ**

`anim_scale` **không tích luỹ xuống chuỗi bone** — giải mã từ
`BoneDynamics.animeproj` đối chiếu bản render của chính Moho. Gốc của bone con
được đặt bằng ma trận đầy đủ (có scale) của bone cha, nên một thân đang squash
vẫn kéo cái đầu xuống; nhưng trục riêng của bone con được dựng lại từ góc xoay
tích luỹ và scale của **chính nó**, nên cú squash không bóp nhỏ con theo.

Tài liệu đó squash `TorsoA` xuống `anim_scale = 0.61` ở frame 1. Nhân ma trận
theo kiểu thường làm tai thỏ co từ 130 px (chiều cao nghỉ, và cũng là của Moho)
xuống 83.5 px — gần đúng 130 × 0.61 — trong khi Moho giữ nguyên 130. Sửa xong
thì mọi bộ đối chứng khác cũng tốt lên (sai số dọc, trung bình / lớn nhất):

| Layer | Trước | Sau |
|---|---|---|
| `Bandit` `Muzzle` | 2.65 / 5.92 px | **0.85 / 2.05 px** |
| `Bandit` `BellyTexture` | 2.84 / 6.26 px | **0.68 / 1.66 px** |
| `SketchBone` `kafasi` | 2.35 / 10.94 px | **1.53 / 2.08 px** |
| `SketchBone` `kulak-sol` | 4.47 / 20.20 px | **3.20 / 6.68 px** |
| `SketchBone` `cizgiler-sag` | 2.20 / 9.51 px | **1.64 / 3.49 px** |


`scaling_mode` — **được dùng**, và đã được giải mã là công tắc "Squash and
stretch scaling" (xem [§ 2.3](#23-từ-bone-đến-ma-trận)). `max_auto_scaling` —
được dùng, như chặn trên cho tự giãn IK. `squash_stretch_scaling` — một độ
lớn (`1.0` trên 831 trong 850 bone), vẫn không dùng.

**Physics / dynamics**

`bone_dynamics` và `angle_dynamics` — **được dùng** cùng nhau làm công tắc
bật/tắt phía sau `--bone-dynamics`, cùng với `spring_force` và
`damping_force` (xem [§ 3.5](#35-bone-dynamics-physics-lò-xo)).

Không dùng: `torque_force`, `pos_dynamics`, `scale_dynamics`,
`wind_dynamics`, các biến thể `pos_` / `scale_` của ba trường lực, ba trường
`*_control_delay`, cộng `physics_radius`, `physics_return_to_zero`,
`physics_motor_speed`, `physics_torque`, `physics_lock_tip`.

Mọi thứ từ `angle_dynamics` trở đi chỉ tồn tại từ **format 1045**; file ở
1021/1038 chỉ mang một bộ ba lực và một công tắc duy nhất.

**Trạng thái editor (không dùng)**

`selected`, `hidden`, `shy`, `bone_label_showing`, `bone_tags`,
`angle_weight`, `pos_weight`, `scale_weight`.

**`flip_h` / `flip_v` — được dùng (đính chính một khẳng định "trạng thái editor" trước đây)**

Các channel bool phản chiếu mọi thứ bone điều khiển, được áp dụng bởi
`Skeleton.world_matrices` đúng cách `Layer.local_matrix` áp dụng các flip của
riêng *một layer*: `flip_h` đảo dấu cột đầu tiên của ma trận (trục hướng riêng
của bone, trục mà `anim_scale` tỷ lệ), `flip_v` đảo cột thứ hai.

Hiếm nhưng có thật: đúng **một** bone khắp 19 tài liệu mẫu từng đặt một trong
hai — `B23` của `SketchBone.animeproj`, mắt cá chân trái điều khiển layer bàn
chân `ayak-sol` qua `flexi_bone_subset` của nó, được keyframe `flip_h` `False`
tại frame 0 → `True` tại frame 44 (một người làm hoạt ảnh xoay bàn chân giữa
chừng bước đi thay vì vẽ lại nó). Trong khi thứ này từng bị xếp vào trạng thái
editor và bị bỏ qua, bàn chân đó render chỉ về phía sau so với hướng di chuyển
của chính nó trong suốt nửa sau của bước đi. Sửa nó cắt sai số pixel của bàn
chân so với các frame tham chiếu đi **51.9%** (đo trên cả 120 frame của
`moho/SketchBone/`).

**Lỗi này đã tái phát một lần, âm thầm, và rất dễ tái phát lần nữa.** `B23`
là bone gốc, nhưng chính con của nó trong cùng `flexi_bone_subset` (`B24`,
`B25`) lại compose dựa trên nó. Một fix sau đó, tự nó đúng (scale của bone
không còn tích luỹ xuống chuỗi — xem [§ 2.3](#23-từ-bone-đến-ma-trận)), đã
thay phép compose ma trận 2x2 đầy đủ bằng phép cộng dồn **góc vô hướng** cho
mọi bone không phải gốc — mà một góc vô hướng thì không thể biểu diễn phản
chiếu (mirror): ma trận của chính `B23` vẫn lật đúng (`det` vẫn âm từ frame
44), nhưng ma trận của `B24` và `B25` thì không — phản chiếu không bao giờ
lan tới chúng, nên `ayak-sol` bị rách so với chính mắt cá chân của nó từ
frame 44 trở đi, trong khi chân (do một nhóm bone khác, không bị lật, điều
khiển) vẫn trông đúng. Chính cái split "chân đúng, bàn chân sai" đó là lý do
nó đọc như cùng một lỗi quay lại thay vì một lỗi mới. Bản sửa (mục "NOTE ON
FLIP PROPAGATION" trong chính `Skeleton.world_matrices`) compose một **ma
trận** cho phần xoay-và-lật tích luỹ, không phải một góc vô hướng, nên `det`
lại nhân đúng xuyên suốt chuỗi. Cả hai phép kiểm dưới đây phải chạy lại sau
**bất kỳ** thay đổi nào vào `Skeleton.world_matrices` hay
`Skeleton._solve_ik_pair`, không chỉ những thay đổi nhắc tới `flip_h` — đây
là lần thứ hai một thay đổi về scale/compose làm hỏng nó mà không hề đụng
vào code xử lý flip:

- **Tức thì, không cần bản đối chứng** — mọi bone tại hoặc sau một lần lật,
  và mọi bone con của nó, phải có `det(world_matrices(f)[i]) < 0`: xem lệnh
  cụ thể trong docstring của `world_matrices`.
- **Đối chiếu bản render của chính Moho** — `make check-reference` giờ chạy
  thêm một phép kiểm *hướng vẽ (winding)* (`tools/check_reference_frames.py`,
  `run_winding_check`, `WINDING_CHECKS`) riêng cho `ayak-sol`, vì phép kiểm
  tâm bounding-box cũ quá yếu để bắt được lỗi này: bounding box gần như
  không đổi (rộng 43.4px lúc lỗi so với 41.9px lúc đúng ở frame 44) trong
  khi hướng vẽ của outline đã lật ngược. Thêm layer vào `WINDING_CHECKS` cho
  bất kỳ bone nào khác có `flip_h`/`flip_v` là một thay đổi keyframe thật.
- **Đối chiếu bản render thật của Moho, cả tài liệu, cả hai chân** —
  `moho/track/SketchBone/foot/` (120 frame, phủ cả `bacak-sag`/`ayak-sag`,
  bone không bao giờ lật, lẫn `bacak-sol`/`ayak-sol`, bone có lật) và
  `moho/track/SketchBone/parts/ayak-sol-{43,44,45,46}.jpg` (bốn ảnh chụp
  crop), cả hai được cung cấp riêng để phân xử bản sửa này. Chỉ riêng ảnh
  chụp thì chưa đủ bằng chứng và đã dẫn tới một chẩn đoán **sai**, đáng ghi
  lại vì phần sửa lại chính là phần hữu ích.

  Sai số theo từng điểm (khoảng cách trung bình điểm-tới-điểm so với bản đối
  chứng) trên cả 120 frame: `ayak-sag` (đối chứng — cùng hình dạng rig,
  không bao giờ lật) không bao giờ vượt quá 5.88px ở bất kỳ đâu. `ayak-sol`
  đạt đỉnh 50.91px ở frame 45, rồi giảm dần xuống dưới 0.5px vào frame 57 —
  một sai số thật, lớn, nhưng **thoáng qua**, không phải vĩnh viễn. Tắt việc
  lan truyền (phương án bản sửa này thay thế) thì tệ hơn rõ rệt: 24-67px từ
  frame 44 trở đi và **không bao giờ hồi phục**.

  **Chính sự kiện lật là nguyên nhân gốc của sai số thoáng qua** — không
  phải một yếu tố phụ kích hoạt một vấn đề đường cong nội suy không liên
  quan (một bản nháp trước của ghi chú này nói đúng như vậy, và đã hạ thấp
  vai trò của chính sự kiện lật; sửa lại sau khi người cung cấp bộ frame đối
  chứng này xem lại Moho App và xác nhận bone target thật sự đổi hướng tức
  thì tại frame 43→44 trong chính Moho). In ra góc **world** của `B24` — bản
  thân `B24` không hề tự lật; đây thuần tuý là kết quả compose qua bone cha
  `B23` đã lật — theo từng frame:

  | Frame | 43 | 44 | 45 | 46 | 47 |
  |---|---|---|---|---|---|
  | Góc world của `B24` | −8.23° | **−146.56°** | −138.86° | −130.01° | −121.65° |

  Một **cú nhảy −138.34° chỉ trong một frame**, sau đó đổi mượt ~7-9°/frame.
  Cú gián đoạn đó — không phải chi tiết hình dạng đường cong nào — mới chính
  là sai số thoáng qua ở khung 44-46, và nó là hệ quả **đúng về mặt toán
  học** của việc compose một phép xoay qua một phép phản chiếu: bản thân
  `B23` chuyển từ góc local 182.87° sang góc world 2.87° ngay khi `flip_h`
  bật (182.87+180 = 362.87 = 2.87° mod 360, đúng khớp với việc phản chiếu
  một cột của ma trận xoay), và keyframe góc local riêng của `B24` (−24.38°,
  cũng đặt đúng tại frame 44, nhỏ và có thật, do animator vẽ) sau đó compose
  qua khung cha vừa bị phản chiếu — đúng là thứ mà một hệ toạ độ bị phản
  chiếu làm với một phép xoay local tiếp theo: nó đảo ngược chiều (handedness)
  biểu kiến của phép xoay đó trong không gian world.

  Đã thử hai công thức compose khác đối chiếu với đúng bộ 120 frame này, cả
  hai đều **bằng hoặc tệ hơn**:
  - Đổi thứ tự, áp flip trong không gian cha *trước* khi xoay bone — kết quả
    y hệt ở đây, vì bản thân `B24` không bao giờ tự lật (đổi thứ tự vô nghĩa
    khi không có gì để đổi).
  - Lan truyền một cờ boolean "mirrored" riêng bằng XOR xuống chuỗi, trong
    khi cộng góc local như số vô hướng thường (không đảo chiều), rồi áp
    gương một lần duy nhất ở cuối — phương án "trực giác" hơn, nhưng tệ hơn
    nhiều: nó không còn hội tụ đúng về trạng thái ổn định nữa (16.70px trung
    bình / 33.08px lớn nhất ở frame 90, so với ~0.3px của cách hiện tại).

  Vậy cú nhảy là có thật, lớn, và là hệ quả trực tiếp, không tránh được của
  việc sự kiện lật compose đúng xuyên suốt chuỗi — không phải một triệu
  chứng cần giải thích cho qua. Điều vẫn còn là chi tiết phụ, chưa rõ, là vì
  sao sai số không giữ nguyên ở đỉnh: nó giảm dần mượt về gần 0 vào frame
  57, đọc ~0 đúng tại các keyframe sau của `B23.anim_angle` (49: 2.26px, 53:
  2.71px, 57: 0.46px) trong khi đạt đỉnh **giữa** các keyframe đó (28px
  trung bình ở frame 45, 12px ở frame 52). `B23.anim_angle` dao động 178° →
  216.4° → 130° → 159.8° đúng qua các keyframe đó — đảo chiều hai lần trong
  14 frame — mà không có tay cầm Bezier tường minh nào (đã xác nhận: `im & 8`
  tắt suốt), tức là đường easing mặc định chưa giải mã của chính Moho, được
  xấp xỉ bằng monotone cubic của `Channel._segment` (xem
  [`moho-animation-and-transform.md`
  § 3.6](moho-animation-and-transform.md#36-thay-vào-đó-mohosvgpy-làm-gì))
  — một điểm thiếu chính xác đã biết từ trước ở nơi khác, bị khuếch đại lớn
  ở đây bởi chiều dài chuỗi và vì nằm chồng ngay lên cú gián đoạn thật của
  chính sự kiện lật.

  **Không phải lỗi blend của `Skinner.deform`** (một bản nháp trước của ghi
  chú này đoán sai điều đó, chỉ dựa trên 4 frame) — một trọng số blend sai
  sẽ không tự về 0 đúng tại các keyframe riêng của `B23` như thế này. Cố
  tình để chưa sửa, vì đường easing thật của Moho chưa được giải mã — xem
  mục KNOWN GAPS của module docstring.

  **Đã đối chiếu với chính Moho App đang chạy**, không chỉ các frame đã
  xuất: người cung cấp bộ đối chứng này đã tua từng frame `ayak-sol` trong
  Moho App từ 44 tới 49 và xác nhận nó vẫn tiếp tục đổi hình/kích thước
  suốt khoảng đó trước khi ổn định — không phải một cú snap gọn trong đúng
  1 frame. Điều này xác nhận `moho/track/SketchBone/foot/` là bản đối chứng
  đáng tin, và giải quyết dứt điểm một câu hỏi lẽ ra sẽ còn lặp lại: **phép
  lật** là tức thời (43→44), nhưng "hình vẫn đổi thêm vài frame sau đó" là
  hành vi thật của chính Moho, không phải hiện tượng do bản sửa này tạo ra.
  Khoảng trống còn lại chỉ là hình dạng **chính xác** trong khung 44-48,
  không phải chuyện việc ổn định mất vài frame.

**Trường hợp đặc biệt: `offset`** — xem [§ 3.7](#37-offset-công-cụ-offset-bone).
Nó được liệt kê dưới "trạng thái editor" trong
[`moho-project-file-format.md` § 9](moho-project-file-format.md#9-bones-và-skinning),
nhưng nó **không** ở giá trị mặc định trong mọi file, nên nó xứng đáng có mục
riêng.

### 2.3 Từ bone đến ma trận

Mỗi bone có một ma trận cục bộ được xây từ các channel pose riêng, rồi hợp với
ma trận world của cha:

```
local = | cos(angle)·scale   -sin(angle)   pos.x |
        | sin(angle)·scale    cos(angle)   pos.y |

world(i) = world(parent) · local(i)      (world(i) = local(i) nếu parent < 0)
```

Hai điều về điều này đáng biết:

- **Chỉ cột đầu tiên được tỷ lệ.** Sự bất đối xứng này là cố ý trong
  `moho2svg.py`: nó khớp với mọi render tham chiếu sẵn có, và không mẫu nào
  dùng một bone có `anim_scale` xa `1.0` theo cách có thể phân biệt tỷ lệ bất
  đối xứng với tỷ lệ đều. `scaling_mode` (giá trị `0` và `2`) là một giải thích
  hợp lý và **chưa được giải mã**. Đừng "sửa" nó nếu không có bằng chứng tham
  chiếu mới.
- **Pose nghỉ là frame 0.0**, không phải keyframe đầu. Xem
  [`moho-animation-and-transform.md` § 2.3](moho-animation-and-transform.md#23-đánh-số-frame-và-frame-0-nghĩa-là-gì).

### 2.4 Một điểm thực sự bị biến dạng thế nào

Với một skeleton tại một frame, biến dạng được xây một lần và dùng lại cho mọi
điểm:

```
rest(i)         = ma trận world của bone i tại frame 0.0
pose(i)         = ma trận world của bone i tại frame được yêu cầu
rest_to_pose(i) = pose(i) · rest(i)⁻¹
rest_p0(i)      = rest(i) áp lên (0, 0)          # gốc bone, pose nghỉ
rest_p1(i)      = rest(i) áp lên (length, 0)     # đầu bone, pose nghỉ
```

Rồi, với một điểm `p` (bind mềm):

```
với mỗi bone ứng viên i:
    nếu strength(i) <= 0: bỏ qua                       # cổng cứng, kiểm tra trước
    d = khoảng cách từ p tới đoạn rest_p0(i)–rest_p1(i)
    w = falloff(d, strength(i))                     # mặc định: 1 / d²
    tích lũy rest_to_pose(i)·p, có trọng số w
p' = trung bình có trọng số, hoặc p không đổi nếu không bone nào đóng góp
```

**Hình dạng suy giảm (falloff) là một heuristic.** `moho2svg.py` mang bốn dạng
(`inv_d2`, `linear`, `cut_d2`, `hermite`) và dùng nghịch đảo bình phương
khoảng cách; không có tham chiếu sẵn có nào tách được chúng, và trường hợp hai
bone cùng có ảnh hưởng mạnh gần một điểm là trường hợp chưa được kiểm chứng.

Chú ý `strength` *không* làm gì trong falloff mặc định: `1/d²` bỏ qua hoàn toàn
giá trị của nó, nên `strength` chỉ hoạt động như một cổng bật/tắt ở đó. Các
falloff `linear`, `cut_d2` và `hermite` thì có dùng nó như một bán kính.

### 2.5 Cách một layer gắn vào skeleton

Điều này được quyết định **theo từng layer**, bởi `parent_bone` trên layer
(không phải bởi bất cứ gì trên bone):

| `parent_bone` | Ý nghĩa | Số lượng (842 layer) |
|---|---|---|
| `>= 0` | **Cứng**: mọi điểm đi theo đúng bone đó. | 54 |
| `-1` | **Mềm / region**: blend có trọng số theo khoảng cách của nhiều bone. | 779 |
| `-3` | Chỉ quan sát trên `ImageLayer`, luôn cùng với `flexi_bone_subset` không rỗng. **Chưa giải mã** — có khả năng là một chế độ warp bone riêng cho raster. `moho2svg.py` rơi về xử lý mềm, điều chưa được xác nhận. | 9 |

Bind mềm có thể được thu hẹp bởi `flexi_bone_subset` trên layer: một **chuỗi**
các **chỉ số** bone nối bằng `"|"`, ví dụ `"4|5|11"`. Không rỗng trên **319
trong 842 layer**, với 1 – 24 chỉ số (trung bình 2.4). Khi nó rỗng, mọi bone
trong skeleton đều là ứng viên.

Sai lầm phổ biến: `flexi_bone_subset` giữ chỉ số *bone*, trong khi
`mesh.groups` giữ chỉ số *điểm* ([§ 6.1](#61-nhóm-điểm-meshgroups)). Chúng là
hai không gian tên khác nhau và không bao giờ tham chiếu lẫn nhau.

### 2.6 Các trường cấp skeleton và cấp bone-layer

| Trường | Ở đâu | Quan sát | Được dùng? |
|---|---|---|---|
| `binding_mode` | `skeleton` | `1` trên 41 skeleton, **`2` trên 1** (`OffsetBoneTool.animeproj`, layer `Happy Dance`). **Chưa giải mã.** | không |
| `bones_groups` | `skeleton` | Chỉ hiện diện trong tài liệu `1045`, và rỗng ở đó. Có lẽ là công cụ hỗ trợ nhóm/chọn bone. | không |
| `grandpa_bone` | `BoneLayer` | `true` trên cả 47 bone layer. Cho phép bones bind các layer lồng sâu hơn con trực tiếp. | không (chuỗi biến dạng đã vượt được lồng sâu tùy ý) |
| `flexi_bone_elbow` | `BoneLayer` | `false` trên cả 47. **Chưa giải mã.** | không |
| `gravity`, `wind` | `BoneLayer` | Môi trường physics của bone; trên đúng một bone layer trong mẫu. | không |

> **Đính chính.** Một bản sửa cũ của
> [`moho-project-file-format.md` § 6.4](moho-project-file-format.md#64-các-trường-riêng-theo-loại)
> nói `binding_mode` là `1` trên mọi skeleton được lấy mẫu. Điều đó sai: một
> skeleton dùng `2`. Vì không có gì rẽ nhánh trên trường đó, không đầu ra nào
> đổi, nhưng khẳng định quá mạnh.

### 2.7 Mỗi thế hệ định dạng đã thêm gì

Bản ghi bone lớn dần theo thời gian. Các trường hiện diện **chỉ** trong tài
liệu `1045` (`Bandit.mohoproj`, 28 bone):

`angle_control_delay`, `pos_control_delay`, `scale_control_delay`,
`angle_dynamics`, `pos_dynamics`, `scale_dynamics`, `wind_dynamics`,
`pos_torque_force`, `pos_spring_force`, `pos_damping_force`,
`scale_torque_force`, `scale_spring_force`, `scale_damping_force`,
`angle_weight`, `pos_weight`, `scale_weight`, `bone_tags`,
`bone_label_showing`, `bone_enable_arc_solver`.

Các trường thiếu chỉ trong tài liệu `1021`: `ignored_by_ik`.

Hệ quả thực tế: một trình đọc phải coi mọi trường bone là tùy chọn và cung cấp
mặc định. Đừng giả định một trường tồn tại chỉ vì một file mới hơn có nó.

---

## 3. Ràng buộc bone và công cụ hỗ trợ rig

Mọi thứ trong phần này đều **được đọc nhưng không được áp dụng** bởi
`moho2svg.py`. Câu hỏi quan trọng với một công cụ xuất không phải "nó có được
cài đặt không?" mà là "bỏ qua nó có làm thay đổi bức tranh không?" — và câu
trả lời khác nhau theo từng tính năng.

Đường phân chia: một tính năng mà Moho **bake vào `anim_angle` / `anim_pos`
khi nghệ sĩ pose** thì an toàn để bỏ qua. Một tính năng mà Moho **đánh giá lúc
phát lại** thì không, vì không có gì trong file chứa kết quả của nó.

### 3.1 Ràng buộc góc

`constraints` (bool), `min_constraint`, `max_constraint` (radian).

- **Đã xác nhận**: `constraints: true` trên **158 trong 850 bone**, khắp 11
  tài liệu. Cặp mặc định là `±1.2217` rad (±70°) — hiện diện trên 735 bone dù
  constraints có bật hay không. Các cặp khác quan sát được hẹp hơn (`±0.4363`
  = ±25°, `±0.1745` = ±10°, `±0.5236` = ±30°).
- **Ảnh hưởng của việc bỏ qua**: không cho một ảnh tĩnh. Constraints giới hạn
  những gì nghệ sĩ có thể chỉnh; góc sống sót qua giới hạn chính là thứ được
  ghi vào `anim_angle`.
- **Nơi nó sẽ quan trọng**: một editor, hoặc một phép giải IK do trình đọc
  thực hiện.

### 3.2 Góc độc lập (`fixed_angle`)

- **Đã xác nhận**: `true` trên **45 trong 850 bone**, khắp 10 tài liệu.
- **Ý nghĩa (suy luận)**: bone giữ một góc cố định trong không gian của
  skeleton thay vì thừa hưởng độ xoay của cha. Đây là cờ "Independent Angle"
  của Moho; `IndependentAngle.animeproj` là file hướng dẫn cho nó và đặt nó
  trên 9 bone.
- **Ảnh hưởng của việc bỏ qua**: **chưa kiểm chứng, và có khả năng nhìn thấy
  được.** Nếu Moho áp dụng nó khi hợp các ma trận world, thì một rig mà bone
  cha xoay sẽ đặt bone con sai góc ở đây. Nếu ngược lại các key của nghệ sĩ đã
  mã hóa sẵn kết quả, bỏ qua nó là miễn phí. Không có render tham chiếu nào
  của một rig `fixed_angle` sẵn có để chốt điều này. Coi như một rủi ro mở
  [🟠 4/10 rằng bỏ qua nó an toàn nói chung].

### 3.3 Control bones

Chín trường, ba nhóm ba: `angle_control_parent` / `angle_control_scale` /
`angle_control_delay`, và tương tự cho `pos_` và `scale_`.

- **Đã xác nhận**: `angle_control_parent >= 0` trên **4 bone**,
  `pos_control_parent >= 0` trên **5**, `scale_control_parent >= 0` trên
  **4** — trong `ControlBones.animeproj` (2 bone bị điều khiển trên cả ba
  channel), `BoneDynamics.animeproj`, `Rabbit.animeproj`, `AddBone.animeproj`.
- Các scale là `1.0` khắp nơi trừ một bone trong `BoneDynamics.animeproj` có
  `pos_control_scale` là `{x: -2.0, y: -2.0}` (một sự đi theo nhân đôi, đảo
  chiều). Các delay là `0` khắp nơi trừ `scale_control_delay: 8` trên một bone
  trong `Bandit.mohoproj`.
- **Ý nghĩa**: góc/vị trí/tỷ lệ của bone A được điều khiển bởi bone B, nhân
  một tỷ lệ, tùy chọn trễ N frame.
- **Ảnh hưởng của việc bỏ qua**: **thật, và được đánh giá lúc phát lại.**
  Channel `anim_*` riêng của bone bị điều khiển không chứa giá trị được điều
  khiển, nên một bone bị điều khiển render như chưa động đậy. Nhỏ trong mẫu
  này (13 channel bị điều khiển tổng cộng), nhưng là một thiếu sót thật, không
  phải lý thuyết.

### 3.4 IK và target bones

`target_bone` (một channel `Val` giữ chỉ số bone), `ik_lock`,
`ik_global_angle`, `ik_parent_target`, `ignored_by_ik`,
`bone_enable_arc_solver`.

- **Đã xác nhận**: `target_bone` được đặt (không phải `-1`) trên **41 trong
  850 bone**, khắp **14 trong 19 tài liệu** — nên đây là công cụ hỗ trợ rig
  được dùng rộng nhất trong mẫu. `ik_lock` là `false` và `ik_global_angle` là
  `0.0` trên cả 850 bone; mọi channel `target_bone` có đúng một keyframe.
- **Ảnh hưởng của việc bỏ qua**: **thường không, đôi khi thật.** Khi nghệ sĩ
  pose chi bằng IK trong editor, các góc đã giải được ghi vào `anim_angle`,
  nên phát lại các channel tái tạo được pose. Nó trở thành thiếu sót khi bản
  thân target di chuyển và phép giải được mong đợi xảy ra lúc phát lại — ví dụ
  một bàn chân ghim vào một target bone đang di chuyển.
- `MaximumIKStrethching.animeproj` và `TargetBone.animeproj` là các file
  hướng dẫn cho hành vi này, và là nơi đúng để kiểm thử một cài đặt IK trong
  tương lai.

### 3.5 Bone dynamics (physics lò xo)

**Công tắc gồm hai trường, và cả hai phải bật**

**Đã xác nhận.** Moho bản mới tách cài đặt này ra: `bone_dynamics` là công
tắc tổng của từng bone, còn `angle_dynamics` nói rằng kênh góc có tham gia.
Trường thứ hai chỉ tồn tại từ format 1045, cùng với `pos_dynamics`,
`scale_dynamics`, `wind_dynamics` và các trường
`*_spring_force` / `*_damping_force` / `*_torque_force` / `*_weight` /
`*_control_delay` riêng của chúng.

Không trường nào một mình là công tắc. `SketchBone` có mặt trong tập mẫu này
**hai lần** — bản gốc 2016 (`.animeproj`, format 1038) và bản lưu lại từ Moho
Pro 14.4 (`.mohoproj`, format 1045) của **cùng một tài liệu**:

| Trường | Bản gốc 1038 | Bản lưu lại 1045 |
|---|---|---|
| `bone_dynamics` | false trên cả 94 bone | false trên cả 94 bone |
| `angle_dynamics` | trường không tồn tại | **true trên cả 94 bone** |

Vậy `angle_dynamics` chỉ là giá trị mặc định của trường mới: chính đường nâng
cấp của Moho đặt nó true trên mọi bone của một tài liệu không hề dùng
dynamics. Còn `bone_dynamics` một mình cũng sai ở format mới theo hướng ngược
lại — `Bandit.mohoproj` có nó true trên **cả 28 bone**, gồm các dial Smart
Bone `EyeBlink`, `HeadTurn`, `SquashStretch` và `EyeMovement`, trong khi
`angle_dynamics` chỉ true trên 2 bone.

Do đó `moho2svg.py` đọc công tắc là `bone_dynamics AND angle_dynamics`, coi
`angle_dynamics` vắng mặt là true — xem `Bone.dynamics_on`. Số bone theo cách
đọc đó:

| Tài liệu | Format | Số bone | Dynamics bật |
|---|---|---|---|
| `WhatIsBone.animeproj` | 1038 | 216 | 52 |
| `AddBone.animeproj` | 1038 | 188 | 21 |
| `BoneDynamics.animeproj` | 1038 | 17 | 7 |
| `Rabbit.animeproj` | 1021 | 15 | 7 |
| `ControlBones.animeproj` | 1038 | 29 | 2 |
| `Bandit.mohoproj` | 1045 | 28 | 2 |
| `SketchBone` (cả hai bản) | 1038 / 1045 | 94 | 0 |

**Nó là channel có keyframe, và Smart Bone điều khiển được**

**Đã xác nhận.** `bone_dynamics` là một **channel** `Bool`, không phải một
cờ. Bone `Main` của `BoneDynamics.animeproj` có `when = [0, 1, 29]`,
`val = [False, True, False]` — dynamics chỉ chạy trong khoảng frame 1–28.
Cùng tài liệu đó đăng ký một **action pose** tên `JumpCycle` trên
`bone_dynamics` của cả sáu bone tai thỏ, nên một dial Smart Bone cũng bật tắt
được tính năng này.

**Các lực**

`spring_force`, `damping_force`, `torque_force`. Bộ ba mặc định là
`2.0 / 1.0 / 2.0`. Chuỗi tai của `BoneDynamics.animeproj` được chỉnh dần từ
gốc ra ngọn, và `torque_force` — trường duy nhất mà công cụ xuất không dùng —
lại biến thiên mạnh nhất:

| Bone | `spring_force` | `damping_force` | `torque_force` |
|---|---|---|---|
| `RearA` / `LEarA` (gốc) | 2.0 | 1.0 | 0.1 |
| `REarB` / `LEarB` (giữa) | 1.95 | 3.0 | 0.45 |
| `REarC` / `LEarC` (ngọn) | 0.8 | 4.4 | 1.9 |

**Ảnh hưởng của việc bỏ qua, và của cách xấp xỉ hiện tại**

**Đã vận hành và nhìn thấy được.** Moho cộng chuyển động lò xo lên trên pose
đã key lúc phát lại. Một công cụ xuất chỉ đọc channel render pose đã key
không có follow-through hay overlap.

`--bone-dynamics` cài một lò xo giảm chấn kéo mỗi bone về góc đã key của
chính nó, và hóa ra đó là nguồn dẫn động sai — xem
[§ 8](#8-các-khoảng-trống-xếp-theo-khả-năng-lộ-ra).

### 3.6 Hành vi tỷ lệ

| Trường | Quan sát | Ghi chú |
|---|---|---|
| `scaling_mode` | `0` trên 586 bone, `2` trên 264 | **Đã giải mã: đây là công tắc "Squash and stretch scaling" theo từng bone của Moho.** `2` = bật (chỉ tỷ lệ dọc theo bone), `0` = tắt (tỷ lệ đều thông thường). Phát hiện trong rig `kafasi` của `SketchBone.animeproj`, nơi hai bone đỡ mỗi tai (`B2`/`B3`, `B4`/`B5`) là `2` và bone thứ ba trong cùng `flexi_bone_subset` (`B20`, `B19`) là `0` — khớp với điều panel ràng buộc bone của chính Moho hiển thị. `Skeleton.world_matrices` giờ chỉ áp dụng sự bất đối xứng cho `2`. |
| `squash_stretch_scaling` | `1.0` trên 831 bone; cũng có `0.41`, `0.61`, `0.7`, `2.0`, `10.0` | Một bone bị tỷ lệ nén/dãn bao nhiêu theo chiều dài của nó. |
| `max_auto_scaling` | `1.0` trên 804 bone; lên tới `10.0` | Chặn trên cho việc tự giãn (IK stretch). |

Bỏ qua cả ba chỉ an toàn khi `anim_scale` vẫn ở `1.0`, điều đúng cho keyframe
đầu của mọi bone trong mẫu nhưng **không** qua thời gian: 3 tài liệu keyframe
`anim_scale` trên nhiều bone (`Bandit` 25, `BoneStrengthTool` 22, `SketchBone`
55).

### 3.7 `offset` (công cụ Offset Bone)

`offset` là một `Vec2` thường (không phải channel).

- **Đã xác nhận**: khác không trên **5 bone**, tất cả trong
  `OffsetBoneTool.animeproj` — file hướng dẫn cho công cụ Offset Bone của
  Moho. Bằng không trên 845 bone còn lại.
- **Quan sát**: trên 5 bone đó, `offset` gần bằng nghịch đảo của `anim_pos`
  (ví dụ `anim_pos = {0.074, 0.667}` với `offset = {0.0, -0.596}`). Điều đó
  nhất quán với mục đích của công cụ: di chuyển nơi một bone *ngồi* mà không
  bind lại artwork vốn đã đi theo nó.
- **Hai cách đọc, cả hai đều nhất quán với dữ liệu** —
  (a) `offset` chỉ dời cách bone được vẽ/sửa, và biến dạng dùng mình `anim_pos`
  (vậy bỏ qua nó là chính xác); hoặc
  (b) `offset` dời gốc thật của bone, và các khoảng cách bind được chụp trước
  khi dời (vậy bỏ qua nó làm đổi trọng số bind mềm, vì `rest_p0` / `rest_p1`
  di chuyển).
  **Chưa giải mã** — một render tham chiếu của Moho cho `OffsetBoneTool.animeproj`
  sẽ chốt nó trong một lần so sánh [🟡 5/10 rằng bỏ qua nó là đúng].
- Chú ý một `offset` hằng số sẽ triệt tiêu khỏi `rest_to_pose`
  (`pose · rest⁻¹`) kể cả dưới cách đọc (b). Chỉ có *phép tính trọng số khoảng
  cách* đổi, nên bất kỳ sai số nào cũng là sai số trọng số mềm, không phải
  dời chỗ thô thiển.

### 3.8 Tóm tắt: bỏ qua mỗi tính năng giá bao nhiêu

| Tính năng | Được bake vào channel? | Giá của việc bỏ qua | Đã vận hành trong mẫu? |
|---|---|---|---|
| Ràng buộc góc | có | không | 158 bone, 11 tài liệu |
| Bone dynamics | **không** | thiếu chuyển động phụ, lớn dần khi xa key | 115 bone, 6 tài liệu |
| Control bones | **không** | bone bị điều khiển không di chuyển | 13 channel, 4 tài liệu |
| IK / `target_bone` | thường | chi sai khi target di chuyển | 41 bone, 14 tài liệu |
| Góc độc lập | không rõ | có thể sai góc child | 45 bone, 10 tài liệu |
| `offset` | không rõ | có thể dời trọng số bind | 5 bone, 1 tài liệu |
| `anim_parent` (đổi cha) | n/a | không — 850/850 khớp `parent` tĩnh | không bao giờ được keyframe |
| các độ lớn `squash_stretch_scaling`, `max_auto_scaling` | n/a | chi tiết độ lớn tỷ lệ | bản thân `scaling_mode` giờ đã được giải mã và dùng |

### Hình dạng falloff không phải là đòn bẩy — đã đo

Falloff trọng số của bind mềm đã bị gắn cờ từ đầu là một heuristic chưa được
kiểm chứng, với lý do kho tài liệu chưa bao giờ vận hành một điểm thực sự nằm
giữa hai bone. `moho/SketchBone/ears/` — bản render tách rời của chính Moho
cho hai cái tai, mà mesh của chúng mỗi cái blend ba bone — là tham chiếu đầu
tiên làm điều đó. Chấm điểm silhouette IoU qua 40 frame trên một họ có tham
số `strength^a / d^p`, cộng một falloff Hermite kiểu region:

| falloff | tai | tay |
|---|---|---|
| `1 / d` | 74.38% | 85.88% |
| `1 / d²` (mặc định) | 74.32% | 85.88% |
| `1 / d³` | 74.32% | 85.88% |
| `strength² / d` | 74.51% | 85.88% |
| `hermite(d / strength)` | **74.67%** | 85.88% |

Cả họ chỉ trải rộng **0.4%** trên tai và **giống hệt từng bit trên tay** — mỗi
layer tay đặt tên một bone duy nhất, nên `Skinner.deform` chuẩn hóa trọng số đi
hoàn toàn và không falloff nào có thể có tác dụng ở đó. Vậy sai số tai còn lại
**không** nằm trong hàm trọng số, và tinh chỉnh nó sẽ là khớp nhiễu. Điều này
xác nhận nghi ngờ ban đầu về mặt định lượng thay vì gỡ bỏ nó: falloff vẫn chưa
được kiểm chứng, nhưng giờ người ta biết nó không phải là nơi sai số còn lại
trú ngụ.

Sai số còn lại của tai giờ được xác định là **sụp đổ thể tích của
linear-blend skinning**, từ việc so DIỆN TÍCH silhouette thay vì vị trí. Qua
các frame 74-80 của `moho/SketchBone/ears/` diện tích tai của Moho gần như
không đổi (27,065 / 27,100 / 27,087 / 27,625 px, trong 2%) trong khi của chúng
ta dao động 10% (22,709 / 21,411 / 24,485 / 26,296) và nhỏ hơn suốt cả chặng.
Đó là dấu hiệu của việc lấy trung bình các *vị trí* đã blend: khi hai bone xoay
rời nhau, trung bình có trọng số của các ảnh của chúng rơi vào bên trong cung,
nên mesh co lại một lượng thay đổi theo góc giữa hai bone. Nó cũng giải thích
vì sao không hàm trọng số nào giúp được — hiện tượng sai nằm trong phương pháp
blend, không phải trong các trọng số.

Hai blend bảo toàn diện tích đã được thử và **không cái nào chấp nhận được**,
cả hai đều đổi độ chính xác vị trí lấy độ chính xác diện tích:

| blend | tai IoU | tỷ lệ diện tích tai | tay IoU |
|---|---|---|---|
| linear blend (hiện tại) | **75.97%** | 0.965 | **88.21%** |
| xoay theo trung bình trên vòng tròn + tịnh tiến trung bình | 75.72% | 0.977 | — |
| blend tâm xoay | 70.62% | 0.980 | 86.88% |

Cả hai đẩy tỷ lệ diện tích về 1.0, xác nhận chẩn đoán, và cả hai đều có điểm
kém hơn nhìn tổng thể, nên linear blend được giữ. Đóng khoảng trống này đúng
cách nghĩa là tìm ra sơ đồ Moho thực sự dùng (hành vi của nó bảo toàn diện
tích *và* đúng vị trí, điều không cái nào trong hai cái này đạt được).

Điều vẫn chưa được giải thích là cạnh dưới của tai vung xa hơn của Moho. Đã bị
loại trừ bằng đo lường tới giờ: hình dạng falloff (ở trên), mọi trường ràng
buộc bone (tất cả ở mặc định trên sáu bone tai — không có control parents,
không giới hạn góc, không dynamics, `anim_parent` chỉ phản chiếu `parent`),
`scaling_mode` (đã giải mã, nhưng những bone đó không bao giờ tỷ lệ), bind
điểm-theo-bone (hai cách đọc, cả hai tệ hơn nhiều), và ngữ nghĩa
`flexi_bone_subset` (bỏ subset đạt 72.27%, tệ hơn việc tôn trọng nó ở 74.32%).

---

## 4. Smart Bones trong một trang

Smart Bones là một phần của hệ thống bone, nhưng cách lưu trữ của chúng là hệ
thống *action*, nên chi tiết nằm nơi khác:
[`moho-project-file-format.md` § 11](moho-project-file-format.md#11-actions-và-smart-bones)
và
[`moho-animation-and-transform.md` § 7](moho-animation-and-transform.md#7-actions-và-smart-bones).

Bản một đoạn, vì một tài liệu về hệ thống bone không trọn vẹn nếu thiếu nó:

Một **dial bone** là một bone có *tên* khớp với tên một action trên cùng bone
layer. Xoay bone đó tự nó không biến dạng gì — thay vào đó, góc hiện tại của
nó được tra **ngược** qua đường cong pose riêng của action cho bone đó
(`Channel.frame_for_value`), tạo ra một số frame bên trong action. Mọi channel
trong tài liệu mang một pose cho action đó sau đó được đánh giá tại frame đó,
ghi đè giá trị bình thường của nó. Đó là cách "xoay dial này 30°" trở thành
"cái miệng hé mở nửa".

Hai hệ quả hay khiến người ta mắc:

- Góc của chính dial bone phải được đọc bằng bộ đánh giá **thô**, bỏ qua cỗ
  máy ghi đè mà nó là một phần — nếu không phép tra cứu đệ quy vào chính nó.
- Trạng thái Smart Bone là một phần của khóa cache skinning: cùng một skeleton
  ở cùng một frame có thể biến dạng khác nhau dưới các action đang hoạt động
  khác nhau.

---

## 5. Smart Warp

### 5.1 Nó là gì — nền tảng, không phải bằng chứng

> **Không có trong mẫu.** Không file nào trong `moho/` dùng Smart Warp: một
> tìm kiếm bất kỳ khóa JSON nào chứa "warp" khắp 19 file trả về **không kết
> quả**. Các đoạn trong tiểu mục này đến từ kiến thức chung về Moho như một
> ứng dụng, không phải từ bất kỳ file nào được xem xét ở đây. Chúng chỉ mang
> tính định hướng — đừng **cài đặt** dựa vào chúng. [🟠 4/10]

Smart Warp là một tính năng biến dạng thêm vào trong thế hệ Moho 13. Thay vì
uốn artwork bằng bones, nghệ sĩ đặt một **warp mesh** lên trên một layer hoặc
một nhóm: một lưới các ô (tùy chọn chia nhỏ, tùy chọn tam giác hóa) bao quanh
artwork. Kéo một điểm warp-mesh uốn mọi thứ bên dưới nó. Vì warp mesh độc lập
với các điểm của chính artwork, nó có thể biến dạng những thứ bones xử lý tệ —
cả một nhóm cùng lúc, các layer raster/ảnh, các đường uốn như vải, nén và dãn
của cả một nhân vật hoàn chỉnh.

Bản thân warp mesh có thể được hoạt ảnh, nên nó có thể được keyframe như bất
kỳ thuộc tính Moho nào, và có thể được điều khiển từ một action (và do đó từ
một Smart Bone dial).

Khác biệt thực tế so với bones, với bất kỳ ai xây một công cụ xuất: biến dạng
bone là *thưa* (một nắm ma trận được blend cho mỗi điểm), trong khi warp mesh
là *dày* (một ánh xạ từng mảnh được định nghĩa bởi một lưới). Chúng không thay
thế nhau được, và một cài đặt chỉ-dùng-bone không thể xấp xỉ cái này bằng cái
kia.

### 5.2 Các file thực sự cho thấy gì

Đây là các quan sát **đã xác nhận**. Việc chúng có thuộc Smart Warp hay không
là suy luận, và được đánh dấu như vậy.

| Trường | Ở đâu | Quan sát | Cách đọc |
|---|---|---|---|
| `distortion_layer_uuid` | mọi layer trong các file `1038` và `1045` (827 layer); **vắng mặt** trong file `1021` | `""` trong cả 827 | Một layer trỏ tới *một layer khác* dùng làm mesh biến dạng. Cái tên khớp mạnh với một tham chiếu warp-mesh. **Suy luận** [🟡 6/10]. |
| `triangulated` | mọi `MeshLayer` trong file `1045` (21); vắng mặt trong `1038` và `1021` | `false` trên cả 21 | Một mesh có thể được tam giác hóa — điều một mesh biến dạng cần và một mesh vẽ không cần. |
| `squashable_deformer` | cùng 21 layer | `false` trên cả 21 | Từ *deformer* ngụ ý một mesh có thể hoạt động như một deformer. |
| `frame_zero_deformer` | cùng 21 layer | `true` trên cả 21 | Có lẽ "deformer này được định nghĩa tại frame 0", khớp với quy ước pose-nghỉ-tại-frame-0 mà bones đã dùng. |

Mô hình theo thế hệ là phần hữu ích: **cả ba cờ deformer chỉ xuất hiện trong
thế hệ định dạng mới nhất của mẫu này (`1045`)**, và không cờ nào tồn tại
trong `1038` hay `1021`. Điều đó nhất quán với một tính năng deformation-mesh
xuất hiện trong cùng họ bản phát hành với các file đó, và nghĩa là một trình
đọc cũ hơn sẽ không bao giờ thấy chúng.

Liên quan nhưng tách biệt: `parent_bone == -3` trên 9 `ImageLayer`, luôn với
một `flexi_bone_subset` không rỗng ([§ 2.5](#25-cách-một-layer-gắn-vào-skeleton)).
Đó là một chế độ biến dạng raster, không phải Smart Warp, và cũng chưa được
giải mã.

### 5.3 Làm gì hôm nay

- **Đừng đoán định dạng.** Không cấu trúc, không tên trường, không bố cục
  điểm nào cho một warp mesh có thể được nói ra từ mẫu này.
- **Hãy phát hiện nó.** Một trình đọc có thể rẻ ràng gắn cờ một tài liệu là
  "có thể không được hỗ trợ" khi bất kỳ layer nào có `distortion_layer_uuid`
  không rỗng, hoặc khi một mesh layer có `squashable_deformer: true`.
  `moho2svg.py` hôm nay không làm cái nào; nó sẽ im lặng xuất artwork chưa
  biến dạng.
- **Để ghi lại nó đúng cách**, một file là đủ: lưu bất kỳ dự án Moho nào dùng
  một Smart Warp mesh vào `moho/`, rồi chạy lại cuộc điều tra trong
  [§ 9](#9-tái-tạo-lại-các-con-số). Các khóa mới sẽ nổi bật ngay, vì tập khóa
  hiện tại đã được liệt kê đầy đủ.

---

## 6. Ràng buộc cấp mesh

Đây là các trường giới hạn hoặc định hình lại biến dạng ở cấp mesh, curve và
điểm — trái ngược với ở cấp bone. Hầu hết đều trơ trong mẫu, nhưng mỗi cái
thay đổi bức tranh khi nó không trơ.

### 6.1 Nhóm điểm (`mesh.groups`)

`[{"type": "PointGroup", "name": "...", "points": [chỉ số vào mesh.points]}]`

- **Đã xác nhận**: không rỗng trên **10 mesh** (trong 648 của mẫu), giữ **14
  đối tượng nhóm điểm** tổng cộng, tất cả trong hai rig hướng dẫn gần như
  giống hệt `ReparentBone.animeproj` và `SelectandReparentBoneTool.animeproj`.
  Các tên quan sát được: `Right Hand` (hai lần), `Left Laces`, `Right Laces`,
  `top lip`, `bottom lip`, `bottom Teeth`.
- Không có gì khác trong các file đó tham chiếu một nhóm theo tên.
- **Cách đọc**: một tiện ích editor để chọn một tập điểm (và mục tiêu tự nhiên
  cho các thao tác cấp điểm như bind một nhóm điểm vào một bone). Bỏ qua nó
  chẳng tốn gì ở đây.
- Đừng nhầm không gian chỉ số với `flexi_bone_subset`
  ([§ 2.5](#25-cách-một-layer-gắn-vào-skeleton)): đây là các chỉ số **điểm**.

### 6.2 Curve profiles

`curve.profile_layer_uuid`, `profile_curve_id`, `profile_repeat`,
`profile_offset`.

- **Đã xác nhận**: không được đặt trong mọi curve — `""`, `-1`, `16`, `0.0`.
  Đó là 1,932 curve trong cây `layers`, hoặc 3,045 nếu đếm cả các mesh lồng
  trong `TextLayer` (quần thể mà
  [`moho-project-file-format.md` § 7.3](moho-project-file-format.md#73-curves-và-curve-points)
  dùng).
- **Cách đọc**: một profile lặp lại hình dạng của một curve khác dọc theo curve
  này (một nét trang trí/hoa văn). Nó ràng buộc hình học được vẽ, không phải
  biến dạng.
- Bỏ qua nó là miễn phí ở đây, và sẽ tạo ra một curve thường thay vì một curve
  có profile trong một tài liệu dùng nó.

### 6.3 Cắt tỉa curve (`start_percent` / `end_percent`)

- **Đã xác nhận**: `start_percent` là `-0.1` trên cả 3,045 curve;
  `end_percent` là `1.1` trên tất cả trừ 3 (là `1.008296`, cùng một curve
  "mũi" dùng chung qua ba file hướng dẫn anh em). Cả hai là **channel** `Val`,
  và không cái nào được keyframe.
- Các mặc định cố ý kéo dài hơi quá cả hai đầu của curve.
- **Vì sao nó quan trọng**: một `end_percent` được keyframe là cách Moho hoạt
  ảnh một nét vẽ tự vẽ lên chính nó. Một trình đọc bỏ qua channel sẽ vẽ toàn
  bộ nét từ frame 0. Không được vận hành ở đây, nhưng đây là một kỹ thuật hoạt
  ảnh phổ biến, nên hãy coi nó là một khoảng trống khả dĩ cho các file sản xuất
  thật hơn là một cái hiếm gặp.

### 6.4 Các cờ deformer trên một mesh layer

`triangulated`, `squashable_deformer`, `frame_zero_deformer` — xem
[§ 5.2](#52-các-file-thực-sự-cho-thấy-gì). Chúng chỉ tồn tại trong thế hệ
`1045` và đều ở mặc định ở đó.

### 6.5 Các đầu vào biến dạng theo layer, gom một chỗ

Khi trả lời "vì sao layer này di chuyển như thế?", đây là các trường để kiểm,
theo thứ tự chúng áp dụng:

1. `parent_bone` — cứng với một bone, mềm, hoặc `-3` chưa giải mã.
2. `flexi_bone_subset` — những bone nào thậm chí là ứng viên.
3. `strength` trên mỗi bone ứng viên — `0.0` loại bone đó hoàn toàn.
4. `transforms` trên layer và mọi tổ tiên — ngăn xếp ma trận thông thường.
5. `origin` — trục xoay cho độ xoay và tỷ lệ riêng của layer.
6. Các action Smart Bone đang hoạt động — chúng có thể ghi đè bất kỳ channel
   nào ở trên.

Chỉ sau cả sáu, hình học riêng của mesh (curves, tái dựng Bezier) mới vào cuộc.

---

## 7. `moho2svg.py` cài đặt những gì

Đã xác nhận bằng cách đọc code (`Bone._build`, `Skeleton.world_matrices`,
`Skinner`, `build_deform_chain`, `Layer.parent_bone`,
`Layer.flexi_bone_subset`).

| Vùng | Trạng thái |
|---|---|
| Phân cấp bone, ma trận world, cha xuất hiện lệch thứ tự | đã cài đặt |
| Bind cứng (`parent_bone >= 0`) | đã cài đặt |
| Bind mềm + `flexi_bone_subset` + cổng `strength` | đã cài đặt, falloff là một heuristic |
| Biến dạng trong không gian riêng của bone layer, ở mọi độ sâu lồng | đã cài đặt |
| Smart Bone dial điều khiển actions | đã cài đặt |
| 2-bone Target IK (`target_bone`) + tự giãn (`scaling_mode`/`max_auto_scaling`) | đã cài đặt — xem `Skeleton._solve_ik_pair` |
| `flip_h` / `flip_v` của bone | đã cài đặt — xem `Skeleton.world_matrices` |
| Ràng buộc bone, control bones, dynamics, `offset`, `anim_parent` | đọc vào mô hình, **không bao giờ áp dụng** |
| `binding_mode`, `grandpa_bone`, `flexi_bone_elbow`, `bones_groups` | bị bỏ qua |

### 7.1 Kiểm toán: trường nào chưa được đọc mà vẫn có thể quan trọng

Mọi trường bên dưới đã được kiểm tra với cả 19 tài liệu mẫu, để tách "chưa đọc
và vô hại ở đây" khỏi "chưa đọc và là một khoảng trống thật". Ghi lại các kết
quả âm tính cũng quan trọng như các kết quả dương tính: nó ngăn cùng một
trường bị điều tra lại về sau.

| Trường | Ở đâu | Phát hiện |
|---|---|---|
| `anim_parent` | bone | **Thừa ở đây.** Không bao giờ được hoạt ảnh, và không bao giờ khác `parent` tĩnh, trên bất kỳ bone nào trong 19 tài liệu — kể cả `ReparentBone.animeproj`, thứ mà toàn bộ chủ đề là đổi cha. |
| `angle_/pos_/scale_control_parent` | bone | Không được đặt trên bone nào của `SketchBone.animeproj`. Có thật nơi khác (`ControlBones.animeproj`), vẫn chưa được áp dụng. |
| `flexi_bone_elbow` | layer | `False` trên cả 101 layer mang nó. Cái tên gợi ý việc làm mịn khớp mà công cụ này thiếu, nhưng không mẫu nào bật nó, nên không thể quan sát tác dụng của nó. |
| `binding_mode` | skeleton | Hầu như hằng số: `1` trên 63 trong 64 skeleton, `2` trên một (`OffsetBoneTool.animeproj`'s "Happy Dance"). Không phải công tắc theo layer. |
| `mesh.points[].parent` | mesh point | **Bind điểm-theo-bone — một tính năng thật, chưa cài đặt.** Xem bên dưới. |
| `mesh.groups` | mesh | Nhóm điểm. Rỗng trên tất cả trừ 10 mesh (`ReparentBone` / `SelectandReparentBoneTool` tay và chân, `Closed`). Vẫn chưa đọc. |
| `layer.timing_offset` | layer | Dời toàn bộ hoạt ảnh của một layer theo thời gian. `0` trên 839 layer, `45` trên 3 — `ProsBox`, `PROS` và `T I  PS` của `Rabbit.animeproj`. **Đính chính một khẳng định trước đây ở đây rằng ba cái đó "lệch nhịp 45 frame":** chúng không lệch, vì cả ba hoàn toàn tĩnh — không channel nào được hoạt ảnh trong toàn bộ cây con của chúng, được xác nhận bằng cách đánh giá lại hình học của chúng tại các frame 1/10/20/29 và nhận đầu ra giống hệt — và 45 vượt quá khoảng 1–29 của chính tài liệu đó. Được đọc và đếm, cố ý không áp dụng: với không gì hoạt ảnh một layer như vậy, dấu (trễ hay sớm?), phạm vi (cây con hay không?) và hành vi dưới một tổ tiên được hoạt ảnh đều không kiểm chứng được, nên áp dụng nó sẽ là ba cú đoán đồng thời mà không có kiểm thử nào có thể thất bại. |

**Bind điểm-theo-bone (`mesh.points[].parent`) được dùng rộng hơn nhiều so
với một bản sửa trước đây của bảng này từng khẳng định.** `MeshPoint._build`
chỉ đọc `position` và `width`, nên trường này bị loại bỏ hoàn toàn. Phân bố
của giá trị trên toàn kho: `-2` trên 7,365 điểm (dùng bind của chính layer),
`-1` trên 551, và **một chỉ số bone cụ thể trên khoảng 4,000 điểm rải khắp
119 mesh**. `Bandit.mohoproj` dựa nhiều vào nó — `Leg_F` bind 9 trong 28 điểm
của nó vào bone 11, `Ears` bind cả 20 điểm khắp các bone 2/20/21/22/23, và
`Body`, `BlueSpot`, `YellowSpot`, `Back_Texture` mỗi cái ghim một phần chính
chúng. Các mesh đó hiện biến dạng theo bind của layer thay vì theo sự gán
từng-điểm rõ ràng của nghệ sĩ.

Nó **không** phải thứ xé tách cánh tay của `SketchBone.animeproj`: mọi điểm
của `kol-sol-ust`/`kol-sol-alt`/`kol-sag-ust`/`kol-sag-alt` là `-2`, và tài
liệu đó dùng bind điểm trên chỉ 2 mesh (cả hai tai, mỗi cái 5 điểm vào bone
0). Vết xé ở tay đến từ việc bind `flexi_bone_subset` một-bone là cứng — xem
`Exporter._effective_subset`.

**Đã cài đặt, đã đo, và để TẮT** (`--point-bones`,
`RenderSettings.point_bone_binding`). Tôn trọng một bone theo-điểm đòi hỏi
biến dạng `mesh.points` *trước* `CurveGeometry.build` thay vì biến dạng các
control point đã hoàn thành sau đó, vì một tay cầm Bezier không thuộc về bất
kỳ điểm đơn lẻ nào nên không có bone nào để đi theo. `Exporter._geometry_and_mapper`
chọn thứ tự đó chỉ cho một mesh thực sự dùng trường này, vì hai thứ tự không
thể hoán đổi — tái dựng tay cầm giao hoán với một phép biến đổi đồng dạng
nhưng không giao hoán với các transform tỷ lệ không đều của layer và sự mang
tỷ lệ bone bất đối xứng của `Skeleton.world_matrices`. (Chuyển *mọi* mesh làm
dịch chuyển các SVG xuất ra của cả năm tài liệu mẫu, riêng `SketchBone.svg`
36,119 dòng.)

Đọc trường này theo kiểu "điểm này đi theo bone đó một cách cứng nhắc" rồi đo
**tệ hơn nhiều**, nên nó không được bật:

| mesh (tai của SketchBone) | err% bỏ qua trường | err% tôn trọng nó |
|---|---|---|
| `kulak-sol/kulak-sol` | 16.0% | **48.4%** |
| `kulak-sag/kulak-sol` | 13.8% | **38.5%** |

Khác biệt toàn-frame đi **sai hướng 78.9%**.

Giả thuyết "nhầm skeleton" sau đó được kiểm thử và **bị bác bỏ**. Chỉ
`SketchBone.animeproj` phân biệt được hai cách đọc — tai của nó nằm dưới
`kafasi` (21 bone) bên trong `cat_boy` (42), trong khi `Bandit.mohoproj` có
một bone layer duy nhất nên cả hai cách đọc trùng nhau ở đó. Chấm trên cùng
vùng tai qua 30 frame:

| nơi chỉ số được phân giải | sai số vùng tai | khác biệt toàn-frame |
|---|---|---|
| trường bị bỏ qua | **14.5%** | **851,143** |
| skeleton trong cùng (`kafasi`) | 40.7% | 1,522,999 |
| skeleton ngoài cùng (`cat_boy`) | 49.4% | 1,587,490 |

Vậy không phải nhầm skeleton: **cả hai** cách đọc cứng đều tệ hơn nhiều so với
bỏ qua trường. Giá trị *là* một chỉ số bone — 123 trong 4,400 điểm được bind
giữ một số lớn hơn số điểm của chính mesh của chúng (`Ears` của Bandit lưu
20–23 cho một mesh 20 điểm), điều loại trừ một chỉ số điểm — nên thứ sai là
cách đọc *cứng*, không phải không gian chỉ số.

Điều còn chưa kiểm thử: một điểm được bind có thể vẫn blend với các điểm lân
cận, với bone được đặt tên chỉ bị ép vào trọng số thay vì chiếm lấy điểm; hoặc
hành vi có thể bị chặn bởi `skeleton.binding_mode`. Cỗ máy vẫn được nối phía
sau `--point-bones` nhưng tắt, nên một lần thử thứ ba bắt đầu từ các phép đo
này thay vì từ một cú đoán.
| `mesh.shape_order` / `anim_shape_order` | mesh | Được điều tra hai lần; **bị bỏ qua một cách đúng đắn** — xem bên dưới. |

**`shape_order` là một sổ đăng ký ID, không phải thứ tự z — đã xác nhận, đính
chính một bản sửa trước đây của phần này.** Nó là một channel `String` chứa
các *ID* của shape. Nó bằng thứ tự file của `mesh.shapes` trong 565 trong 614
mesh, và **khác trong 49** — `Bandit.mohoproj` (5/21), `IndependentAngle` /
`MaximumIKStrethching` / `TargetBone` (12/28 mỗi cái), `OffsetBoneTool` (6/19),
`BoneDynamics` / `Rabbit` (1 mỗi cái). Một bản sửa trước đây đọc điều đó là
"49 mesh bị vẽ sai thứ tự z". **Điều đó sai.** Trong **47 trong 49** danh sách
ID tăng nghiêm ngặt trong khi thứ tự file thì không, đó là vẻ ngoài của một sổ
đăng ký chứ không phải của một thứ tự z do nghệ sĩ chọn (`Arm_B`: lưu
`"1|6|7|9|10"`, thứ tự file `10|9|6|1|7`, gần như đảo ngược); 2 ngoại lệ,
`Leg_F`/`Leg_F 2` của Bandit, cũng gần tăng. Sắp xếp lại theo nó cũng làm vỡ
nhóm `combo_mode`, thứ được xây từ sự liền kề trong thứ tự file — render
Bandit theo cách đó abort thay vì vẽ. Cả hai phát hiện khớp với thí nghiệm
độc lập được ghi trong chính docstring của `moho2svg.py`. `Mesh.draw_order()`
giờ nêu quy tắc ở một nơi duy nhất. `SketchBone.animeproj` không bị ảnh hưởng
theo cách nào (0/82), và `anim_shape_order` là `false` trên cả 614 mesh, nên
không tài liệu mẫu nào hoạt ảnh thứ tự z của nó.

**Vết xé khớp giữa hai nửa bị bind cứng KHÔNG được giải thích bởi bất kỳ
trường chưa đọc nào.** Một layer có `flexi_bone_subset` đặt tên đúng một bone
biến dạng cứng nhắc (`Skinner.deform` chuẩn hóa theo trọng số đơn, nên falloff
triệt tiêu). `SketchBone.animeproj` bind từng nửa cánh tay theo cách đó -
`kol-sol-ust`→bone 13, `kol-sol-alt`→bone 14, `kol-sag-ust`→15,
`kol-sag-alt`→16 - nên khi khuỷu tay cong, hai nửa xoay quanh các trục khác
nhau và tách rời nhau. Đo trên các đường viền được render: khe hở giữa
`kol-sol-ust` và `kol-sol-alt` giữ ở 1-9 px tới frame 51, rồi nhảy lên 40 px tại
frame 56 và ổn định quanh 26 px, bám chính xác cú vung 41.5 độ của chính bone
14 giữa các keyframe của nó tại frame 49 và 55. Bản thân skeleton vẫn vững
suốt (đầu bone 13 tới gốc bone 14 là hằng số 7.8 px), và không nửa nào được
hoạt ảnh điểm, hoạt ảnh transform layer, hay được tỷ lệ không cứng - nên đây
là mô hình bind, không phải các bone. "Smooth Joint for Bone Pair" của chính
Moho là tính năng sẽ blend qua một khớp như vậy, và **không tìm thấy trường
lưu trữ nào cho nó**: cuộc kiểm toán ở trên loại trừ mọi ứng viên. Đóng khoảng
trống này nghĩa là phát minh một phép blend, điều mà falloff đã bị gắn cờ là
chưa được kiểm chứng cho ([§ 2.4](#24-một-điểm-thực-sự-bị-biến-dạng-thế-nào)).
| `parent_bone == -3` | rơi về bind mềm, chưa xác nhận |
| Smart Warp / distortion layers | **không cài đặt, không phát hiện** |
| Nhóm điểm, curve profiles, `start_percent` / `end_percent` | bị bỏ qua |

---

## 8. Các khoảng trống, xếp theo khả năng lộ ra

1. **Bone dynamics** — bật trong 6 trên 19 tài liệu, được đánh giá lúc phát
   lại, ảnh hưởng mọi frame xa một key. Khoảng trống thật lớn nhất trong mẫu
   này. **Đã cài đặt phía sau `--bone-dynamics`, tắt theo mặc định** — xem
   `Skeleton.dynamic_angles`.

   Bone được mô hình hoá như một con lắc có quán tính trong không gian
   **world**. Với `pw` là góc world của bone cha và `x` là góc local của
   chính bone:

   ```
   x'' = spring·(keyed − x) − damping·(x' + pw') − pw''
   ```

   Hai số hạng `pw` mới là điểm mấu chốt. Bản trước chỉ kéo bone về góc đã
   key của chính nó, nên một bone có `anim_angle` không bao giờ đổi thì không
   bao giờ động đậy — mà trên toàn tập mẫu đó lại là trường hợp thường gặp:

   | Tài liệu | Dynamics bật | `anim_angle` riêng có đổi | Giờ có phản ứng |
   |---|---|---|---|
   | `BoneDynamics.animeproj` | 7 | **0** | có, ±27.5° |
   | `Rabbit.animeproj` | 7 | **0** | có, ±21.7° |
   | `WhatIsBone.animeproj` | 52 | 16 | có, ±63.7° |
   | `AddBone.animeproj` | 21 | **0** | không |
   | `ControlBones.animeproj` | 2 | **0** | không |
   | `Bandit.mohoproj` | 2 | **0** | không |

   `BoneDynamics.animeproj` cho thấy vì sao phải viết lại. Cả sáu bone tai
   giữ nguyên `anim_angle`, `anim_pos` và `anim_scale`; thứ chuyển động là
   bone ông nội `Main` (`anim_pos` x −1.56…1.10, y −0.32…1.43 — cú nhảy) và
   `TorsoA` (góc 250°…307°). **Tai vẫy vì nó trễ so với chuyển động world của
   bone cha.**

   Ba tài liệu còn "không" là những tài liệu có bone dynamics treo dưới một
   bone cha chỉ **tịnh tiến**. Muốn chúng phản ứng thì cần số hạng gia tốc
   điểm treo — đúng vai trò tự nhiên của `torque_force` — và điều đó đã được
   thử rồi bác bỏ bằng bằng chứng, hai lần: nó làm ngọn tai của
   `BoneDynamics.animeproj` vọt lên 81° ở một frame, và khi quét từ 0.001 tới
   1.0 đối chiếu bản render của chính Moho cho `Bandit.mohoproj` thì không
   lần nào cải thiện, còn ở 1.0 làm chóp đuôi tệ đi (sai số dọc 32.15 px →
   35.76 px). Nên `torque_force` vẫn được đọc mà không dùng.

   **Đơn vị tính theo frame, không theo giây.** Đọc theo giây thì spring 2 và
   damping 1 tạo ra một dao động lỏng tới mức chuyển động xoay của bone cha
   kéo bone lệch 200° khỏi góc đã key rồi giữ nguyên ở đó. Đây là một phép
   khớp, không phải giải mã.

   **Cái đuôi của Bandit chính là hình dạng của khoảng trống này.** Mọi layer
   của tài liệu đó bám bản render của chính Moho trong khoảng 0.3–2.8 px, trừ
   hai layer ở đuôi, lệch 18 px (gốc) tới 32 px (ngọn) theo phương dọc — mà
   hai bone đuôi lại đúng là hai bone duy nhất có dynamics. Trong bản đối
   chứng, nhịp nhún của đuôi là bản sao nhịp nhún của thân, **trễ 4 frame**
   (tương quan chéo 0.93 tại đó, so với −0.91 tại độ trễ 0) và **biên độ tăng
   dần xuống chuỗi** (độ lệch chuẩn 6.7 px ở mõm, 10.0 ở gốc đuôi, 15.1 ở
   ngọn). Trễ cộng với khuếch đại chính là dao động cộng hưởng. Chuyện bind đã
   được loại trừ riêng: cả 28 kiểu gắn cứng, 5 subset và cả 4 falloff đều để
   lại sai số dọc chênh nhau chưa tới 2 px.

   **Giờ đã có bài kiểm, và nó trượt.** `moho/BoneDynamics/` (29 frame, bản
   xuất của chính Moho) là ca sạch: 6 trong 7 bone dynamics là hai tai thỏ,
   không bone dynamics nào tự đổi góc, không bone nào đăng ký gió. Bật
   `--bone-dynamics` làm tai **tệ đi**: sai số vị trí trung bình 60.6 px →
   62.6 px (tai phải), 65.2 → 66.0 (tai trái). Mô hình không chỉ là chưa kiểm
   chứng — nó đo được là **không cải thiện**, và đó là lý do vẫn để tắt.

   Nhưng phải đọc kỹ: nền cũng đang tệ. Khi tắt dynamics, hai tai đó đã lệch
   sẵn ~60 px, so với 0.3–3.5 px của mọi layer trong hai tài liệu đối chứng
   còn lại — nên còn thứ khác sai trong rig đó, và tín hiệu dynamics bị lấn
   át. Đã loại trừ: kế thừa scale (đã sửa riêng — đưa tai từ ~78 px xuống
   ~60 px), bốn công thức trục ngang của `squash_stretch_scaling`, bốn hàm
   falloff, control bones (ba bone điều khiển của nó gần như đứng yên), và
   chính trọng số skin (kiểm từng điểm — mỗi điểm tai đều bị bone gần nhất áp
   đảo trên 95 %).

   Chi phí: trạng thái tại frame F phụ thuộc mọi frame trước nó, nên mỗi lần
   gọi mô phỏng từ frame bắt đầu. Đo từ đầu tới cuối trên một bản xuất Lottie
   đầy đủ — `Bandit` 6s → 9s, `WhatIsBone` ~35s → 1m45s. Moho cộng chuyển động
   phụ kiểu lò xo/tắt dần lên trên pose đã key, nên bỏ qua nó khiến chuyển
   động đọc như *gắt hơn* so với Moho, chứ không phải bớt gắt hơn. Control bones
   (`angle_/pos_/scale_control_parent`) được đặt trên 9 bone khắp 4 trong số
   các tài liệu đó. **Không cái nào được dùng ở bất kỳ đâu trong
   `SketchBone.animeproj`** — cả năm skeleton của nó (`cat_boy` 42 bone,
   `kafasi` 21, `el-sol` 11, `el-sag` 11, `Sketch` 9) có không cái nào của mỗi
   loại, nên không cái nào giải thích được hành vi tai của rig đó.
2. **Hình dạng falloff của bind mềm** — bốn ứng viên giờ đã **phân biệt
   được**, và chúng mâu thuẫn nhau. Chấm bằng `make check-reference` (tổng sai
   số vị trí trung bình trên các layer mỗi tài liệu chạm tới được):

   | Falloff | SketchBone, 10 layer | Bandit `TailBase` dx | Bandit `Belly` dy |
   |---|---|---|---|
   | `inv_d2` (mặc định) | **34.15** | 8.25 px | 3.02 px |
   | `cut_d2` | 35.54 | 6.38 px | 3.02 px |
   | `hermite` | 41.53 | 2.02 px | 1.62 px |
   | `linear` | 43.58 | **1.89 px** | **1.59 px** |

   Nhóm có tầm ảnh hưởng hữu hạn thắng mọi layer Bandit trộn nhiều bone, và
   thua mọi layer SketchBone tương đương (`kuyruk` 2.37 → 6.24 px, `golge`
   6.48 → 10.47 px). **Vậy không cái nào trong bốn là hàm thật của Moho.**
   `inv_d2` vẫn là mặc định vì thắng trên bộ đối chứng rộng hơn — 10 layer so
   với 3, và ở format mới hơn.

   Điều này cũng giải thích vì sao trước đây không phân biệt được: một layer
   mà một bone áp đảo sẽ cho kết quả *y hệt* dưới cả bốn. `Tip` của `Bandit`,
   chỉ bind vào hai bone, đúng là ca đó.

3. **Smart Warp** — vô hình ở đây (0 file), nhưng một tài liệu dùng nó sẽ mất
   toàn bộ biến dạng một cách im lặng. Phát hiện thì rẻ; hỗ trợ thì không.
4. **Hoạt ảnh `end_percent`** — không được vận hành ở đây, phổ biến trong sản
   xuất.
5. **Control bones** — nhỏ trong mẫu này, nhưng mất trắng nơi được dùng.
6. **IK với target di chuyển** — thường được bake, đôi khi không.
7. **Góc độc lập (`fixed_angle`)** — 45 bone; ảnh hưởng chưa kiểm chứng.
8. **`offset`, `binding_mode == 2`, `parent_bone == -3`, `scaling_mode`** —
   chưa giải mã, mỗi cái được quan sát ở đúng một chỗ hẹp.

---

## 9. Tái tạo lại các con số

Mọi số đếm ở trên đến từ một bước duyệt JSON đơn giản. Mẫu:

```python
import json, glob, collections

files = sorted(glob.glob('moho/*.mohoproj') + glob.glob('moho/*.animeproj'))
stats = collections.Counter()

def walk(layer):
    skel = layer.get('skeleton')
    if isinstance(skel, dict) and skel.get('bones'):
        for bone in skel['bones']:
            stats[bone.get('constraints')] += 1        # thay bằng bất kỳ trường nào
    for child in layer.get('layers') or []:
        walk(child)

for path in files:
    for layer in json.load(open(path)).get('layers') or []:
        walk(layer)

print(stats)
```

Các biến thể hữu ích:

- Điều tra các trường bone theo thế hệ định dạng: khóa counter bằng `version`
  cấp cao nhất của tài liệu (`1021` / `1038` / `1045`) cùng với trường.
- Tìm một tính năng vắng mặt: grep văn bản thô theo tên khóa, ví dụ
  `grep -o '"[a-z_0-9]*warp[a-z_0-9]*"' moho/*.animeproj | sort -u` — đây là
  cách khẳng định "không kết quả Smart Warp" trong [§ 5.1](#51-nó-là-gì--nền-tảng-không-phải-bằng-chứng)
  được kiểm tra.
- Giá trị của một channel: đọc `val[0]` cho keyframe đầu và `len(when)` cho số
  key. Một trường như `bone_dynamics` là một channel, không phải bool, và đếm
  nó như bool sẽ cho câu trả lời sai.
