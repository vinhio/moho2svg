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

**Hành vi tỷ lệ (không dùng)**

`scaling_mode`, `squash_stretch_scaling`, `max_auto_scaling`.

**Physics / dynamics (không dùng)**

`bone_dynamics`, `angle_dynamics`, `pos_dynamics`, `scale_dynamics`,
`wind_dynamics`, `torque_force`, `spring_force`, `damping_force`, và các biến
thể `pos_` / `scale_` của ba trường lực, cộng `physics_radius`,
`physics_return_to_zero`, `physics_motor_speed`, `physics_torque`,
`physics_lock_tip`.

**Trạng thái editor (không dùng)**

`selected`, `hidden`, `shy`, `bone_label_showing`, `bone_tags`, `flip_h`,
`flip_v`, `angle_weight`, `pos_weight`, `scale_weight`.

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

- **Đã xác nhận**: `bone_dynamics` là `true` trên **115 trong 850 bone**, khắp
  6 tài liệu — `WhatIsBone` (52), `Bandit` (28, tức mọi bone trong file),
  `AddBone` (21), `BoneDynamics` (6), `Rabbit` (6), `ControlBones` (2). Nó là
  một **channel** `Bool` và được keyframe trong `BoneDynamics.animeproj` (14
  channel có nhiều hơn một key khắp mẫu).
  `angle_dynamics` là `true` trên 2 bone trong `Bandit.mohoproj`; các dynamics
  `pos_`, `scale_` và `wind_` là `false` khắp nơi.
- **Ảnh hưởng của việc bỏ qua**: **đã vận hành và nhìn thấy được.** Moho cộng
  chuyển động lò xo lên trên pose đã key lúc phát lại. Một công cụ xuất chỉ
  đọc channel render pose đã key không có follow-through hay overlap, và sai
  số lớn dần theo khoảng cách tới một keyframe.
- Các lực tạo hình nó: `spring_force`, `damping_force`, `torque_force` (22
  bone của Bandit dùng chung `2.0 / 1.0 / 2.0`, 6 cái được chỉnh riêng).

### 3.6 Hành vi tỷ lệ

| Trường | Quan sát | Ghi chú |
|---|---|---|
| `scaling_mode` | `0` trên 586 bone, `2` trên 264 | **Chưa giải mã.** Giải thích hợp lý nhất cho tỷ lệ bone bất đối xứng được giữ trong `Skeleton.world_matrices` ([§ 2.3](#23-từ-bone-đến-ma-trận)). |
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
| họ `scaling_mode` | n/a | hành vi tỷ lệ không rõ | 264 bone dùng chế độ `2` |

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
| Ràng buộc bone, control bones, IK, dynamics, `scaling_mode`, `offset`, `anim_parent` | đọc vào mô hình, **không bao giờ áp dụng** |
| `binding_mode`, `grandpa_bone`, `flexi_bone_elbow`, `bones_groups` | bị bỏ qua |
| `parent_bone == -3` | rơi về bind mềm, chưa xác nhận |
| Smart Warp / distortion layers | **không cài đặt, không phát hiện** |
| Nhóm điểm, curve profiles, `start_percent` / `end_percent` | bị bỏ qua |

---

## 8. Các khoảng trống, xếp theo khả năng lộ ra

1. **Bone dynamics** — bật trong 6 trên 19 tài liệu, được đánh giá lúc phát
   lại, ảnh hưởng mọi frame xa một key. Khoảng trống thật lớn nhất trong mẫu
   này.
2. **Smart Warp** — vô hình ở đây (0 file), nhưng một tài liệu dùng nó sẽ mất
   toàn bộ biến dạng một cách im lặng. Phát hiện thì rẻ; hỗ trợ thì không.
3. **Hoạt ảnh `end_percent`** — không được vận hành ở đây, phổ biến trong sản
   xuất.
4. **Control bones** — nhỏ trong mẫu này, nhưng mất trắng nơi được dùng.
5. **IK với target di chuyển** — thường được bake, đôi khi không.
6. **Góc độc lập (`fixed_angle`)** — 45 bone; ảnh hưởng chưa kiểm chứng.
7. **Hình dạng falloff của bind mềm** — ảnh hưởng mọi layer mềm một chút; chỉ
   nhìn thấy nơi hai bone chồng mạnh.
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
