# Third-Party Notices

本目錄下的化學工具（`ChemLatex.html`、`Chem2D.html`、`mol2chemfig-js/`、`vendor/`；
線上部署於 `StandardMeanOceanWater/public` 的 `tools/`）除原創程式碼外，另散布或衍生自以下
第三方開源軟體。專案本身之原創碼採 MIT 授權（見上層 `LICENSE`，© 2026 Jin Lin）；下列元件
各自保留其原授權，其著作權與授權條文一併重製於本檔，以符合各授權之要求。

---

## 1. mol2chemfig-js（衍生作品）

`mol2chemfig-js/` 為 **mol2chemfigPy3** 的 JavaScript 移植（以 RDKit.js 取代 Indigo），
屬其衍生作品。mol2chemfigPy3 本身為原始 **mol2chemfig v1.5**（Python 2）之 py2→py3 翻譯。

上游致謝：

- **mol2chemfigPy3** — © 2021 Nianze Tao (Augus1999)，MIT 授權。
  <https://github.com/Augus1999/mol2chemfigPy3>
- **原始 mol2chemfig v1.5** — Eric K. Brefo-Mensah 與 Michael Palmer（University of Waterloo）。
  文件：<https://mirror.ox.ac.uk/sites/ctan.org/graphics/mol2chemfig/mol2chemfig-doc.pdf>

直接相依（mol2chemfigPy3）之授權全文：

```
MIT License

Copyright (c) 2021 Nianze TAO

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## 2. RDKit / RDKit.js

`vendor/rdkit/`（`RDKit_minimal.js` + `.wasm`，v2025.03.4）為 RDKit 之 WebAssembly 建置，
供 `ChemLatex.html` 與 `mol2chemfig-js/` 使用。

```
BSD 3-Clause License

Copyright (c) 2021-2022, Valence Discovery Inc., Greg Landrum, Paolo Tosco, and other RDKit contributors
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from
   this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

---

## 3. smiles-drawer

`vendor/smiles-drawer.min.js`（v2.0.1）供 `Chem2D.html` 與 `ChemLatex.html` 繪製 2D 結構式。

著作權人：Daniel Probst, Reymond Group, University of Berne。授權：MIT。
上游：<https://github.com/reymond-group/smilesDrawer>

```
MIT License

Copyright (c) Daniel Probst, Reymond Group, University of Berne

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## 4. 資料來源（禮貌性致謝，非隨附程式碼）

本工具於執行期查詢下列公開資料庫 / API。這些為外部服務，非隨附散布之程式碼，
但依其使用規範致謝：

- **PubChem**（NCBI）— 化合物名稱、SMILES、2D 座標、PNG。
- **UniProt** — 蛋白質查詢後援。
- **Wikipedia / Wikidata** — 中文條目對照；維基百科正文內容採 CC BY-SA。
- **MyMemory Translation API** — 繁中→英文名稱翻譯。
- **RCSB PDB、AlphaFold、MolView、ChemTube3D、COD、Materials Project、CCDC/CSD** — 外部連結導引。
