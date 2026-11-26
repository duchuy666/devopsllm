# RB 10 Build Go ARM64 và migration testbed

## Mục tiêu và trạng thái

Giảm phần giả lập ở payment, catalogue, user sau các OOM nền. Ba service đã build linux/arm64 từ tag tương ứng upstream, dùng Go 1.23.12 cross-compiler trên Mac M2. Không tự nâng dependency: khôi phục từng package theo full commit trong vendor manifest/glide.lock gốc. Compiler và dependency cũ được chọn để tái lập ứng dụng development; không tuyên bố là một stack mới được hỗ trợ production.

Đây là thay đổi môi trường/thực thi có chủ ý. Không gộp kết quả cũ với mới như cùng cấu hình frozen hoặc suy ra tác động chỉ do ARM64: compiler và một compatibility patch cũng thay đổi. Những service/database còn lại chưa được chuyển native.

## Source và provenance

`infra/native/sources.lock.json` ghi repository/tag/commit/dependency-lock hash. `toolchain.lock.json` ghi SHA256 archive chính thức từ go.dev. Build output ở `.runtime/native-builds/<service>/`: binary hash, dependency content hash nếu có, compatibility patches, image tag/ID. Source/dependency/toolchain/cache nằm trong `.runtime`, không vào context Gemini hoặc Git.

```bash
.venv/bin/python scripts/prepare_native_sources.py
.venv/bin/python scripts/build_native_go.py payment
.venv/bin/python scripts/build_native_go.py catalogue
.venv/bin/python scripts/build_native_go.py user
```

Compiler tạo binary static với CGO disabled, Linux/ARM64, GOPATH mode và network resolution của Go bị tắt. Helper chỉ tải source đúng commit đã khóa. Repository bị mất hoặc package không có trong lock thì dừng, không đổi sang latest.

## Compatibility patch đã phát hiện

Native user ban đầu xuất `_links.self={}` và các link khác rỗng. Struct upstream dùng anonymous string không export; probe Go 1.23 tái hiện JSON không có href. Patch `user-href-compat.patch` đổi thành field URL export với cùng tag JSON href, giữ API contract cũ. Patch áp dụng trên build worktree, giữ original source checkout và ghi hash trong metadata.

`user_href_contract_test.go` kiểm JSON self/customer/addresses/cards. Sau patch, Go unit test package users đạt. Không tuyên bố đây là rebuild nguyên byte của image cũ. Hai migration lỗi được giữ nguyên: lần đầu register ECONNREFUSED ngay sau rollout; lần sau checkout lỗi do link contract.

## Đóng gói local

```bash
bash -c 'source scripts/common.sh; .venv/bin/python scripts/package_native_go.py payment'
bash -c 'source scripts/common.sh; .venv/bin/python scripts/package_native_go.py catalogue'
bash -c 'source scripts/common.sh; .venv/bin/python scripts/package_native_go.py user'
```

Image scratch có binary/assets/license, user 10001 và không push registry. Payment standalone đã đạt health/authorise/decline và 100 request stub lặp; mức RAM ~3,8MiB chỉ là mẫu đọc riêng, không là benchmark dài hạn.

## Migration và rollback

Không chạy cùng soak/chaos. Native loader giữ shared experiment lock, kiểm binary/image IDs, nạp image vào Minikube, lưu rollback manifest và deployment snapshot, rồi sinh manifest với `active-images.json`.

```bash
bash -c 'source scripts/common.sh; .venv/bin/python scripts/deploy_native_go.py'
```

Manifest vẫn ở `infra/sock-shop/local-emulated.yaml` vì phần còn lại còn giả lập; annotation ghi rõ mode mới. Image local có imagePullPolicy Never, Pod có source commit/binary hash. User được bổ sung env database/link-domain tương ứng image gốc. CPU/RAM cap và DB/PVC giữ nguyên trong lần migration native.

Sau rollout, script probe health từ frontend qua Service tới cả ba service trước checkout để kiểm dataplane đã hội tụ. Không coi Deployment Available tự chứng minh routing sẵn sàng. Checkout vẫn lỗi thì lưu log, rollback manifest/config và đợi rollout cũ; không biến smoke lỗi thành thành công bằng cách bỏ qua request lỗi.

Migration `results/native-migration/20261121T232147Z/` đã đạt 2/2 checkout, 18 request, 0 lỗi. Log/metric/trace và trace liên service kiểm tra đạt lại. Cần soak mới cho môi trường mới trước candidate runner; chưa chứng minh OOM dài hạn đã hết.

## Memory gate

Raw memory.current gồm cả cache. Lần đo sau native có khoảng 1GiB inactive_file. Gate mới dùng working set ước tính `max(0, memory.current - inactive_file)`, giữ nguyên ngưỡng 95%, cùng PSI và node-local OOM; không drop cache hoặc tăng cap để ép đạt.

Cách ước tính theo [cAdvisor source đã ghim](https://github.com/google/cadvisor/blob/8164b38067246b36c773204f154604e2a1c962dc/container/libcontainer/handler.go#L776-L789). Working set không phải toàn bộ lượng bộ nhớ không thể reclaim, cũng không chứng minh không thể OOM. Soak ghi cả raw usage/cache/working set và method, receipt gate version `cgroup-working-set-v1`.

Chạy soak 600 giây theo RB09. Không build/package/load/rollout image trong lúc soak. Giữ kết quả cũ và mới tách theo manifest hash; admission chính thức vẫn cần protocol, effect và near-duplicate review.

Sau migration, soak 600 giây đạt 327 checkout không lỗi. Runner S0011 đã chạy CPU shipping, xuất đủ dữ liệu và phục hồi. Kết quả mới chỉ ở mức calibration; xem `docs/progress/SHIPPING-RUNNER-COMPARISON.md`.
