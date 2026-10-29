## Root review addendum — 2026-10-30

Root approves the exact CP311 manylinux x86_64 NumPy 2.3.5 artifact below
for isolated INTERNAL CI COMPUTATION ONLY. This bounded execution decision does
not approve customer redistribution or add NumPy to application/runtime locks,
images or releases. The earlier worker's pending status below is historical;
customer notice, exact native source correspondence and redistribution closure
remain open. No licence-audit exception is authorized.

The additional collected artifact is
`numpy-2.3.5-cp311-cp311-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl`,
SHA-256 `8cba086a43d54ca804ce711b2a940b16e452807acebe7852ff327f1ecd49b0d4`.
Its manifest records Requires-Dist [] and 22 native files. Root retained the
wheel, full embedded texts and file hashes in the ignored local evidence
manifest, alongside the three platform artifacts reviewed below. The new lock
must install only this artifact with hashes, binary-only and no-deps flags.

Root's actual pip-audit report for NumPy 2.3.5 found no known package-level
vulnerabilities at capture. That result does not close bundled native component
CVE assessment. CI numerical tests prove mechanics on explicitly synthetic
fixtures; they do not establish provider-history quality or forecast accuracy.

---
# NumPy 2.3.5 Runtime Artifact Review — 2026-10-29

**Status: REVIEW NEEDED — root decision pending.** This is an actual-artifact review, not legal clearance, approval, or acceptance on root's behalf. CVE review remains a separate root-gathering input. This report is an implementation prerequisite, not a deferral of the goal.

## 1. Scope, artifacts, and identity

The three wheels below were collected externally through authorized root orchestration and were **not executed or imported** in this review. SHA-256 values and `requires_dist` are taken from the actual `manifest.json`, not from a prior brief.

| Target | Wheel | Wheel SHA-256 | `requires_dist` |
| --- | --- | --- | --- |
| Windows x64 / CP311 | `numpy-2.3.5-cp311-cp311-win_amd64.whl` | `a414504bef8945eae5f2d7cb7be2d4af77c5d1cb5e20b296c2c25b61dff2900c` | `[]` |
| musllinux x64 / CP311 | `numpy-2.3.5-cp311-cp311-musllinux_1_2_x86_64.whl` | `396084a36abdb603546b119d96528c2f6263921c50df3c8fd7cb28873a237748` | `[]` |
| musllinux ARM64 / CP311 | `numpy-2.3.5-cp311-cp311-musllinux_1_2_aarch64.whl` | `6cf9b429b21df6b99f4dee7a1218b8b7ffbbe7df8764dc0bd60ce8a0708fed1e` | `[]` |

All three manifest records have `version: 2.3.5` and `license_expression: null`; the manifest lists `requires_dist` as empty for every wheel. No dependency resolution or binary execution is inferred from that field.

## 2. Historical tool block — resolved collection note

The earlier collection attempt failed before any command ran because of a harness ACL error:

```text
CreateFileW failed (Win32 5): C:\Users\qqshu\AppData\Local\Temp\dsh-acl-locks\50fd8c0a8ec2bb2a.lock
```

That was a tooling failure, not evidence about NumPy. Root resolved collection externally; the error is preserved only as provenance and is **not the current blocker**.

## 3. Texts actually reviewed and hash identity

The full `numpy-2.3.5.dist-info/LICENSE.txt` was read to EOF from extracted evidence:

- musllinux x86_64: 971 lines, 47,768 bytes, SHA-256 `2046a3130e50b11c01659b3a0d963e6ae0b7436ff8e89cbcfd9e87bc6112d595`.
- Windows x64: 950 lines, 46,841 bytes, SHA-256 `596b953e1dcbe829b32ae444387efa15003fc6abdeca8a2179f364a6364c286e`.
- musllinux ARM64: manifest SHA-256 `2046a3130e50b11c01659b3a0d963e6ae0b7436ff8e89cbcfd9e87bc6112d595`, same 47,768 bytes as x86_64, so its text is byte-identical to the reviewed x86_64 text. Path: `evidence/numpy-2.3.5-cp311-cp311-musllinux_1_2_aarch64/numpy-2.3.5.dist-info/LICENSE.txt`.

This is full-license review, not METADATA-only review. The consolidated text covers NumPy, OpenBLAS, LAPACK, GCC runtime, and (in the musl text) libquadmath. The wheels also carry `numpy/ma/LICENSE`, `numpy/random/LICENSE.md`, and `numpy/_core/include/numpy/random/LICENSE.txt`; their hashes are recorded below. They are additional notices to preserve, but are not separately interpreted in this pass.

| Additional text | musl x64 + ARM64 SHA-256 / size | Windows SHA-256 / size |
| --- | --- | --- |
| `numpy/ma/LICENSE` | `05f3b88351988ecfad10abe92c0c50e5875c6452d5009a0084cc291551ffcca6` / 1,593 | `d78dbb208b80d92b4d333e41a4baae50d12444f46e53199fa7726a91de6e2da7` / 1,616 |
| `numpy/random/LICENSE.md` | `103166b62b80443afb9eb3488e052ea06be0cff566b908f199e561fde49af19f` / 3,511 | `b4bc2f4fa1c95778f1ed3dd8f14706bece399475b978f9f34b5d3cd72521b48a` / 3,582 |
| `numpy/_core/include/numpy/random/LICENSE.txt` | `fbc539f47d0cf83bc61378080fb873d5c14630126cacbfe754035c3926daa5ec` / 1,018 | `d544761558b510866c21f7e8a2d5716fca76e0b98117e3b6b86314db7244d150` / 1,039 |

## 4. Actual license classification

**NumPy core — BSD-3-Clause.** The full text requires, for binary redistribution: "Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution." It also prohibits endorsement using NumPy contributors' names. No source-offer condition appears in this BSD text; notice reproduction is the stated binary condition.

**Bundled OpenBLAS — BSD-3-Clause.** The text names `numpy.libs/libscipy_openblas*.so` (musl) and `numpy.libs\libscipy_openblas*.dll` (Windows), and requires reproduction of the copyright notice, conditions, and disclaimer in binary-distribution materials. This is a notice obligation, not a source-offer obligation on the face of the BSD text.

**Bundled LAPACK — `BSD-3-Clause-Open-MPI`.** The text says LAPACK is "bundled in OpenBLAS" and names the same OpenBLAS files. It has the three BSD-style conditions plus a patent/IP disclaimer. Binary redistribution requires the notice, conditions, and disclaimer in documentation/materials; the text states no separate source-offer condition.

**GCC runtime family.** The musl text classifies `libgfortran*.so` as `GPL-3.0-or-later WITH GCC-exception-3.1`; the Windows text classifies the GCC runtime as **statically linked inside** `libscipy_openblas*.dll` under the same expression. The exception says: "You have permission to propagate a work of Target Code formed by combining the Runtime Library with Independent Modules … provided that all Target Code was generated by Eligible Compilation Processes. You may then convey such a combination under terms of your choice." That supports combining independent target code, but it does not itself state a source offer for the runtime binary.

The same `LICENSE.txt` includes GPLv3 §6: "You may convey a covered work in object code form … provided that you also convey the machine-readable Corresponding Source under the terms of this License." Whether/how that applies to these runtime files is a root/counsel compliance question; it is not decided here.

**libquadmath — LGPL-2.1-or-later, musl x86_64 only.** The text says libquadmath may be redistributed/modified "under the terms of the GNU Library General Public License … either version 2.1 … or any later version," and gives a URL. No full LGPL-2.1 body and no source offer are included in the reviewed `LICENSE.txt`; this is an actual notice/source-delivery gap to resolve before conveying that artifact.

## 5. Per-artifact inventory and remaining obligations

### Windows x64

Actual native bundle: `numpy.libs/libscipy_openblas64_-9e3e5a4229c1ca39f10dc82bba9e2b2b.dll` (SHA-256 `9e3e5a4229c1ca39f10dc82bba9e2b2bf48037790932566f37aff1a7ccf3588f`) and `numpy.libs/msvcp140-a4c2229bdc2a2a630acdc095b4d86008.dll` (SHA-256 `a4c2229bdc2a2a630acdc095b4d86008e5c3e3bc7773174354f3da4f5beb9cde`), plus 19 NumPy extension modules. There are **no separate** `libgcc`, `libgfortran`, or `libquadmath` files; the GCC runtime is reported as static in OpenBLAS.

Remaining: attach NumPy/OpenBLAS/LAPACK notices and disclaimers; resolve the source-offer position for the statically embedded GCC runtime; review the `msvcp140` Microsoft redistributable's separate terms, as NumPy's `LICENSE.txt` does not classify or supply a license for that DLL. No CVE conclusion is drawn.

### musllinux x86_64

Actual native libraries include `libscipy_openblas64_-55393b74.so` (`a489d9c3241a5e8a021765196a8146a73987aa080f404605d3c555aa80f4c02d`), `libgfortran-2c33b284-17a27ac2.so.5.0.0` (`9ccbaa99e84534479f54105865a5ce0aefefb520931708fa4e0f906f5fc3f840`), `libquadmath-bb76a5fc-feb0f212.so.0.0.0` (`d4ec9368851b5b34c06def31adbfc98a8c9ac71aefb5680cd144c619b03a1a2c`), `libstdc++-5d72f927.so.6.0.33` (`7e88311ec981d7f0fa0be6bffae1e1f048bfe90879d9af2f2e589c2513377a19`), and two `libgcc_s` files: `libgcc_s-0cd532bd-c8f934f9.so.1` (`6286f37709ecedee1bbcffd46e48258507a4a68528b93f4b3ccfde0022ef5698`) and `libgcc_s-0cd532bd.so.1` (`c8f934f958f22b3b9c8e790fde6bc2d2f55ab9ae8b9f5eea65425b20271782d0`), plus 19 NumPy extension modules.

Remaining: BSD notice reproduction; LGPL-2.1 notice and source-delivery plan for `libquadmath`; exact source/notice mapping for `libgfortran`, `libstdc++`, and both `libgcc_s` files. The bundled text names `libgfortran` but not `libstdc++` or `libgcc_s` as licensed objects. The GCC exception language supports target-code combination, not an automatic source offer for those runtime binaries. No CVE conclusion is drawn.

### musllinux ARM64

Actual native libraries include `libscipy_openblas64_-1fc386ee.so` (`035e499dc30640ed889b4f969090f4146c67f383d61d23b3981de5ec6462d03c`), `libgfortran-67378ab2-e7e7cfab.so.5.0.0` (`9bf532015393794c08b2df43cf97bb4ecac1c55127efadab722c243e5ddc6ae8`), `libstdc++-85f2cd6d.so.6.0.33` (`5634fa1f7ac66c8529d366a459fe6c268cfc2e27d4678385649606391fcac9e2`), and two `libgcc_s` files: `libgcc_s-2d945d6c-767fb991.so.1` (`0586fc2417614fa79bd4b70353bd191748e4b7552f859f286829aa6f5168bdee`) and `libgcc_s-2d945d6c.so.1` (`767fb99107fa5e41168413b1eed9d73191c94126c37526263e1af1f1f898788f`), plus 19 NumPy extension modules. Unlike x86_64, no `libquadmath` file is present.

Remaining: BSD notice reproduction; exact source/notice mapping for `libgfortran`, `libstdc++`, and both `libgcc_s` files; no libquadmath obligation is supported by the actual ARM64 inventory, but that does not remove the other GNU-runtime questions. No CVE conclusion is drawn.

## 6. Root decision

Root can now choose whether to authorize this reviewed NumPy runtime integration, or require a notice/source-offer remediation plan before deployment. This agent does **not** accept on root's behalf and makes **no legal claim**. Status remains **REVIEW NEEDED** until root explicitly decides. CVE identification remains a separate root-gathering task; no vulnerability statement is made here.

No requirement, lock, Dockerfile, CI, policy, or other document was edited. No wheel was executed or imported, and no network or CVE query was performed.
