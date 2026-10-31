# 数据结构与组成原理 30 张知识卡独立复核

复核日期：2026-10-31。复核人与 30 张卡的作者不同。本报告根据现有卡片、已实际打开的来源及评审侧答案逐条审阅；“部分支持”只针对所列规则，不代表整张卡或年度大纲归属已获外部证明。来源原文与商业教辅内容没有复制到公开卡片。

示例与自测答案按卡片可见上下文人工复算；另外用独立 Python 算术检查了性能、补码、二维数组、哈夫曼权重、循环队列、最短路径、AOE、总线、Cache、IO开销与流水线的具体数值。这些检查不替代未核外部来源，不证明 60 卡整体质量。

## 原始问题清单（以下七项均已复审解决）

1. **CO-ISA-001，P1：**自测要求将字段10用于立即寻址，但没有给出立即数字段位宽与扩展／符号解释。若4位 `1010` 符号扩展可得到−6；应在题中指定非负立即数或位宽及零扩展，再与评审侧答案绑定。
2. **CO-CACHE-001，P2：**例题和自测仅引用“给定／其余条件”，应在题目中写出或明确携带16位字节地址、64 B块、256行和直接映射；否则单独作为题目呈现时条件不完整。卡片完整上下文中的计算正确。
3. **DS-SEARCH-002，P2：**B+范围查找应涵盖“没有不小于下界的键”的空结果；不能必然假设存在包含该键的叶结点。
4. **CO-CACHE-002，P3：**“同步更新下一级”建议改为“写直达要求将写入传播到下一级，完成时机和写缓冲按实现约定”，以免被理解成物理同时完成。评审侧自测也应与该限定一致。

5. **DS-TREE-001，P2：**标题包含二叉树性质，但正文只提及满／完全树的区别而未给定义或典型性质。建议补充适用条件明确的基本性质及两个形态定义，避免读者无法从卡片掌握所标主题。
6. **CO-DATA-001，P2：**标题包含定点数，正文主要解释整数补码，未说明定点小数的小数点约定。应补必要表示条件或明确卡片仅覆盖整数补码。
7. **CO-ALU-001，P2：**标题宽泛地说整数运算，正文主要处理补码加减；应补乘除法关键边界或明确当前覆盖范围，不能让读者误以为已讲完整数乘除。

## 逐卡复核

| ID | 本次核对 | 来源支持范围或待核 | 复核时文件 SHA-256 |
| --- | --- | --- | --- |
| `DS-ALG-001` | 单次扫描Θ(n)、辅助空间Θ(1)及嵌套翻倍自测Θ(n log n)正确；平均情况需分布，已有注明 | 外部数学定义与所有复杂度判据待核。 | `7da66dba6d80772859a87297f2bed80617c590f54566179fa97bbfb2c17eebd3` |
| `DS-LIST-001` | 在下标1插入需移动3项；尾插移动0，题设容量足够 | Princeton LinkedQueue 的链结点机制为部分支持；顺序表插入开销未逐项外部核验。 | `d918f3da9f2ed4e1caee6b26c5b370ca669c9091094446f3a461873dee2ade70` |
| `DS-STACK-001` | B、C、A与C、B、A均符合栈次序，递归深度与调用总数有区分 | LinkedStack 的 LIFO 与 push/pop 支持栈操作；递归调用栈的全部细节待独立核验。 | `f2e0f849f32cdb38b707f284dea12ed0671d8b858889e979c236e82b60f24626` |
| `DS-QUEUE-001` | 长度5、front3/rear1为3项；front2/rear1为满，均符合预留空槽约定 | LinkedQueue 支持FIFO与队头队尾；循环数组满空判定为项目给定约定，须单独核验。 | `ebedbc465a3bc3edd01d1c1165202f7e23d8fd5501e7745e31dfcc0a2deab6ff` |
| `DS-ARRAY-001` | 行优先地址136和124、三阶含对角上三角6项均正确 | WG14 C草案 §6.5.2.1 ¶3 支持C语言行优先；该引用不证明所有语言或压缩矩阵方案。 | `2174470244a81f50fb794c323736feb09fac797ff1ba0ac8097ec530246fe93a` |
| `DS-TREE-001` | 复审通过：补齐层数约定、最大结点数、有限非空二叉树n₀=n₂+1及满／完全二叉树，并限定英文full的不同用法；遍历及层序正确。 | DepthFirstOrder只支持图DFS前后序框架；新增二叉树性质与定义仍待专门外部来源核对。 | `85a42e87c3033cfc89b308966d35fec9f72a6fc1cdf5c744a545626ca4b5aefe` |
| `DS-TREE-002` | 权1/2/4的WPL为10；权1/1/2自测为6；等权可能不唯一 | Huffman.buildTrie 实际每次合并两个最小权；WPL与编码非唯一部分独立计算，未由该代码全面证明。 | `dcfd1d8af6ac0a0feb1d8bb8063b3298625ab910cb5e82ac1e92621f4bf767b9` |
| `DS-SEARCH-001` | 2/1/3平衡、中序1/2/3；1/2/3普通BST根高差2，正确 | BST.put提供左小右大插入实现；AVLTreeST.balance/rotate 支持旋转维持平衡；其他边界依卡中互异键约定。 | `245382df35403384e555d33ac5fc62c7cc653b9f26996490191b474a83383ec4` |
| `DS-SEARCH-002` | 复审通过：下界查找允许叶链末尾无匹配并返回空；全小于12的自测为空，无须遍历全部叶。 | Cornell CS6320 第25页支持叶层和叶链；B树其他删除实现细节仍未全面外部核对。 | `f98202c75310a71aea7fd92541ca3e4a9e2023c2ba06e093a085106db7dad39a` |
| `DS-SEARCH-003` | 闭区间查找7依次比较5、7；查3首次保留[0,1]，正确 | BinarySearch.indexOf 支持有序数组闭区间；SequentialSearchST 与 SeparateChainingHashST 分别支持对应实现，性能依条件。 | `7b587dcf4b094e0312c73e87e1907a2bbb3d739e52132c75e207489a72d43c3f` |
| `DS-GRAPH-001` | 字母序BFS为 A B C D，A至D最少2边 | BreadthFirstPaths.bfs 支持队列/标记与无权最短边数；有向图与全图断连遍历细节须对应实现。 | `216043e114a55bf22fcf828a2efe1f5f5a503e35ef7df3f3caee79b5624ee215` |
| `DS-GRAPH-002` | 三角图最小权和3；AC改2时两棵最优树，正确 | KruskalMST 的排序和并查集跳环支持该构造；此实现不足以单独证明卡片所有Prim与森林情形。 | `01323246a4ddc38efd8b0789ffdca51bc9cc9bd2e6265f8d2c64cbf0e090be44` |
| `DS-GRAPH-003` | A-B-C代价5优于7；直接边改4后最短4 | DijkstraSP 构造器拒绝负权，支持给定示例适用边界；负环等内容仍需另源。 | `8b7b1dc3c92da7e744bf6d9780a93f40f8862ba0e30deb4f7f0844fe73757286` |
| `DS-GRAPH-004` | A-B-D=5、A-C-D=6，工期6；改后两路径均5 | Topological 与 AcyclicLP 分别支持DAG排序和最长路径；事件最迟时刻及AOE关键活动判据未被两份源码完整证明。 | `09517c068e7f5a21dc50a8eae36cd1f35ab6154bd14c13d80d083c792d25f611` |
| `DS-SORT-001` | 稳定排序例题B、A、C正确；反转相同键顺序不稳定 | Merge.merge 以左段先取相等键实现稳定归并且使用辅助数组；快排、堆排和选择排序的全部复杂度/稳定性未逐项外部核验。 | `22a6bc23c3457c96d861256424bc4e4fd8e1ad3c8301f1a363fdbff42a1e6cf0` |
| `CO-PERF-001` | 2×10^9×1.5/(3×10^9)=1秒；CPI1.2为0.8秒 | Cornell课程讲义第16页包含加权CPI及主频/CPI关系；跨平台比较和全部假设仍依卡片限定。 | `cee35e0b6e9d89368f8cdacf09a53a54712bd3daa3f13fbc0d9385aa65e7506c` |
| `CO-DATA-001` | 复审通过：补齐4位补码、符号位加3个小数位的缩放约定；1101为整数−3或该小数约定−3/8，自测1010为−6。 | Cornell补码课件支持1101的整数解释；补充的定点小数缩放规则仍需专门来源。 | `6ec0105f9d865cdb7ace90076ae09eced18f2dca48e02b4f81f0de9b2b7f8b4a` |
| `CO-DATA-002` | 单精度1.0符号0、指数01111111、23位小数全0；-1符号变1 | Cornell Floating Point 指数偏置与1/8/23位支持例题；零/非规格化/NaN细节尚未逐项外部核验。 | `11696c0d0f890691e848ca4978e70b951ef338dfc4f6e92d2d0967828cc76f5f` |
| `CO-ALU-001` | 复审通过：补充截断乘法和非零除法的边界；4位−8÷−1的精确商8不可表示，5+3也溢出，自测−1+1=0无溢出。 | Cornell补码／C溢出资料支持定长背景；新增乘除法与具体实现异常仍待专门外部核对。 | `06b1d4b74a7cad8b4281d9ba3de3de701f172f6781209b41b7cd5de2c6621936` |
| `CO-MEM-001` | 2片位扩展×2组字扩展共4片；仅1K×8需2片 | 尚无本轮实际阅读的一手来源支持芯片片选与扩展，保留项目推导、外部待核。 | `4e2a231cdac339252ccd3e155092f5042a7db2213aaf477b906a35ed9a697b5d` |
| `CO-CACHE-001` | 复审通过：例题和自测均单独给出字节编址、块大小、行数和映射方式；字段2/8/6与自测标记18正确。 | Cornell Caches/Larger Blocks 支持三字段与块偏移；具体算数已独立核验。 | `bb81633b069fafa1a14068dd969aa1c37fb3f7240c00972b7020973cccdd5423` |
| `CO-CACHE-002` | 复审通过：写直达改为传播到下一级并明确写缓冲完成时机；AMAT例题2 ns及新自测一致。 | Cornell Caches/Write Policies 支持直达／写回与脏位；写缓冲具体完成时机按实现限定。 | `517ff6153de825bff654a79cd3647af39480d50416242902c19ff3edd34dd85e` |
| `CO-ISA-001` | 复审通过：自测已指定8位无符号字段00001010和零扩展，结果10；直接寻址例题仍为7。 | Cornell Processors 的wrimm为特定实现支持；其他寻址模式及机器差异仍需另源。 | `1f130c79ca133867efb056c150b94e7ae74881371c12fe7aa4804d45c369ec38` |
| `CO-CPU-001` | 给定顺序、长度1时下条101；长度2则102 | Cornell CPU Architecture 的5阶段与仅load/store访存支持阶段区分；PC增长值取决于题设，本例为算术推导。 | `99e488348b478f2c98e90d411ee33d6d4cc86a49f02e676ef09dd50e0a0ef2e7` |
| `CO-CPU-002` | 3条微指令×1周期=3，自测5条=5 | 本轮未读取足以核验微程序控制及微地址转移的来源；该部分外部待核。 | `33b1291b6b84ef79d15a420f30991099dae78ecfe651eaa1c821c48b43368c6c` |
| `CO-PIPE-001` | 5级、3条、无停顿共7周期；1条5周期 | Cornell CPU Architecture / Architecture Styles 给出理想5级4+n周期；具体冒险与前递行为需具体数据通路或另源。 | `15eb8e28c5f160f72e1a9410f418d6030e5f8efeb626588a096eef3c1e2507bd` |
| `CO-BUS-001` | 32位×10^6次/秒=4×10^6字节/秒；16位为2×10^6 | OSTEP I/O Devices §36.1 支持总线／层级背景；仲裁类型与理论带宽公式本轮无直接来源，保留外部待核。 | `c02d1f4e29f9e92d6d5a1ca51a06bfdd1d0f7e2364e5757b00133235a19c90c6` |
| `CO-IO-001` | 允许/优先级满足时需保存返回信息及必要现场；被屏蔽的可屏蔽中断不立即响应 | OSTEP I/O Devices §36.4 支持中断处理背景；优先级、精确现场及屏蔽/保持机制需按题设或另源核验。 | `a9031b9ac0f65674b94cf7af88f0ba3c0717848f461b8a1319c3c30c0a6d582a` |
| `CO-IO-002` | 100字每次1字为100次；每次2字为50次 | OSTEP I/O Devices §36.5 支持DMA由处理器设置传送参数并由DMA协调传送、完成时通知；具体仲裁和一致性待核。 | `54927c808a90cf7480b601d300b992b74ac3d463e3a597b8c49b69a7f88d3d67` |
| `CO-IO-003` | 轮询20000、中断10000、自测30000周期/秒，正确 | OSTEP I/O Devices §36.3–36.4 及提示段支持轮询与中断成本随负载变化；具体数值均为题设算术。 | `5c8f40f0efc734c1ffca15cbb2645dd6292409f63279903b83f1fa6448657f87` |

## 修改后的独立复审绑定（2026-10-31）

以上七处由原作者修正后，本审阅者重新读取实际卡片及对应自测答案，按题设重新推导。七项问题在当前树已解决；相关外部来源仍只按逐卡表所列范围认定。保留原始审核哈希以便追溯。

| ID | 原始审核 SHA-256 | 修正后复审 SHA-256 |
| --- | --- | --- |
| `CO-ISA-001` | `2cd4ccf632788c5659e210bb7fb4bcf6a0e37aa457415ace83ffc0009ba5291e` | `1f130c79ca133867efb056c150b94e7ae74881371c12fe7aa4804d45c369ec38` |
| `CO-CACHE-001` | `6fe3cf83a35df6b71785eecbecaf17d1b45f0fa9044ace97dd75e308ac60d25b` | `bb81633b069fafa1a14068dd969aa1c37fb3f7240c00972b7020973cccdd5423` |
| `DS-SEARCH-002` | `796e5a4b05b64093d060c591e6c18e10a7128e63a328897a33df28c4a411442b` | `f98202c75310a71aea7fd92541ca3e4a9e2023c2ba06e093a085106db7dad39a` |
| `CO-CACHE-002` | `257f15c4e4c1b576dae4841442d0c09c85fafd74a67d95520e8b973a0d76d303` | `517ff6153de825bff654a79cd3647af39480d50416242902c19ff3edd34dd85e` |
| `DS-TREE-001` | `ab9b6375dd4301e070da8f4acd5ac522ed930a7c19589d7cbd256abafccc632a` | `85a42e87c3033cfc89b308966d35fec9f72a6fc1cdf5c744a545626ca4b5aefe` |
| `CO-DATA-001` | `c857b3ba1029fc4356d6771fd79a73ba2615576cf1230a166628b4ed05920e02` | `6ec0105f9d865cdb7ace90076ae09eced18f2dca48e02b4f81f0de9b2b7f8b4a` |
| `CO-ALU-001` | `c8c843fbb192acfcac90d6ba586efa2b809c54c8ec825ae7ab704c0ae9fbb640` | `06b1d4b74a7cad8b4281d9ba3de3de701f172f6781209b41b7cd5de2c6621936` |

## 本轮实际读取的可定位一手来源

1. [Princeton LinkedStack.java](https://raw.githubusercontent.com/kevin-wayne/algs4/master/src/main/java/edu/princeton/cs/algs4/LinkedStack.java)：类说明及 `push`／`pop`。源码为可变分支，本次读取日期见本报告。
2. [Princeton LinkedQueue.java](https://raw.githubusercontent.com/kevin-wayne/algs4/master/src/main/java/edu/princeton/cs/algs4/LinkedQueue.java)：类说明及 `enqueue`／`dequeue`。
3. [WG14 N1570 C语言委员会草案](https://www.open-std.org/jtc1/sc22/wg14/www/docs/n1570.pdf)：§6.5.2.1 第3段、PDF第98页；限定支持C多维数组行优先。
4. [Princeton BST.java](https://raw.githubusercontent.com/kevin-wayne/algs4/master/src/main/java/edu/princeton/cs/algs4/BST.java) 的 `put` 与 [AVLTreeST.java](https://raw.githubusercontent.com/kevin-wayne/algs4/master/src/main/java/edu/princeton/cs/algs4/AVLTreeST.java) 的 `balance`／旋转。
5. [Cornell CS6320 索引课件](https://www.cs.cornell.edu/courses/cs6320/2019sp/Slides/Indexing_final_version.pdf)：B+-Trees structure，PDF第25页。
6. [Princeton BinarySearch.java](https://raw.githubusercontent.com/kevin-wayne/algs4/master/src/main/java/edu/princeton/cs/algs4/BinarySearch.java) 的 `indexOf`；[SequentialSearchST.java](https://raw.githubusercontent.com/kevin-wayne/algs4/master/src/main/java/edu/princeton/cs/algs4/SequentialSearchST.java) 类说明；[SeparateChainingHashST.java](https://raw.githubusercontent.com/kevin-wayne/algs4/master/src/main/java/edu/princeton/cs/algs4/SeparateChainingHashST.java) 类说明。
7. [Princeton BreadthFirstPaths.java](https://raw.githubusercontent.com/kevin-wayne/algs4/master/src/main/java/edu/princeton/cs/algs4/BreadthFirstPaths.java) 的 `bfs`；[DepthFirstOrder.java](https://raw.githubusercontent.com/kevin-wayne/algs4/master/src/main/java/edu/princeton/cs/algs4/DepthFirstOrder.java) 的前后序。
8. [Princeton KruskalMST.java](https://raw.githubusercontent.com/kevin-wayne/algs4/master/src/main/java/edu/princeton/cs/algs4/KruskalMST.java) 的构造器；[DijkstraSP.java](https://raw.githubusercontent.com/kevin-wayne/algs4/master/src/main/java/edu/princeton/cs/algs4/DijkstraSP.java) 的非负权检查；[Topological.java](https://raw.githubusercontent.com/kevin-wayne/algs4/master/src/main/java/edu/princeton/cs/algs4/Topological.java) 与 [AcyclicLP.java](https://raw.githubusercontent.com/kevin-wayne/algs4/master/src/main/java/edu/princeton/cs/algs4/AcyclicLP.java) 的类说明。
9. [Princeton Huffman.java](https://raw.githubusercontent.com/kevin-wayne/algs4/master/src/main/java/edu/princeton/cs/algs4/Huffman.java) 的 `buildTrie`；[Merge.java](https://raw.githubusercontent.com/kevin-wayne/algs4/master/src/main/java/edu/princeton/cs/algs4/Merge.java) 的 `merge` 与辅助数组。
10. [Cornell CS3410 性能／补码课件](https://www.cs.cornell.edu/courses/cs3410/2014sp/lecture/08-perf-pipeline-i-notes.pdf)：PDF第5页补码例子、第16页CPI加权；[Floating Point](https://www.cs.cornell.edu/courses/cs3410/2026fa/notes/float.html) 的32位表示及指数偏置；[Introduction to C](https://www.cs.cornell.edu/courses/cs3410/2026sp/notes/cintro.html) 的 Overflow 段。
11. [Cornell Caches](https://www.cs.cornell.edu/courses/cs3410/2026sp/notes/caches.html)：Larger Blocks、Write Policies；[CPU Architecture](https://www.cs.cornell.edu/courses/cs3410/2026fa/notes/arch.html)：The 5 Classic CPU Stages、Architecture Styles；[Processors](https://www.cs.cornell.edu/courses/cs3410/2026sp/notes/proc.html)：`wrimm` 示例。
12. [OSTEP I/O Devices](https://pages.cs.wisc.edu/~remzi/OSTEP/file-devices.pdf)：§36.1、§36.3–36.5。只支持上述设备交互背景，不作为所有体系结构实现的统一规范。

本报告记录独立复核证据，本审阅者未修改受审卡片。七项修正已重新核对并绑定新哈希；以后卡片再变化时须复审和重新绑定。未核来源仍不得标记为已核。

## 自测独立呈现修订后再次复审（2026-10-31）

保留上方历史哈希和七项修复记录。本轮重新读取全部30张卡及两份评审答案；22条补充题设后的自测可脱离例题理解，题设数据与对应评审答案相符。对其余8条同样重新核对题面及答案。此前的自测公开答案重叠问题另见 review-self-check-disclosure.md，不因条件完整而消失。来源归属建议见 ds-co-source-attribution-suggestions.json；仅标实际阅读可支持的有限范围。

| ID | 本轮文件 SHA-256 | 自测与答案 |
| --- | --- | --- |
| `CO-ALU-001` | `06b1d4b74a7cad8b4281d9ba3de3de701f172f6781209b41b7cd5de2c6621936` | 条件可独立理解；评审答案对应 |
| `CO-BUS-001` | `31dcfce34752408160fcf64099d063ec3f103085d37729cb7753621abd9bd285` | 条件可独立理解；评审答案对应 |
| `CO-CACHE-001` | `bb81633b069fafa1a14068dd969aa1c37fb3f7240c00972b7020973cccdd5423` | 条件可独立理解；评审答案对应 |
| `CO-CACHE-002` | `517ff6153de825bff654a79cd3647af39480d50416242902c19ff3edd34dd85e` | 条件可独立理解；评审答案对应 |
| `CO-CPU-001` | `34e74fa163bc05b2682be33709df52a4a1aff2a52ffb04a3023eb84ec2901bb1` | 条件可独立理解；评审答案对应 |
| `CO-CPU-002` | `e38306c4e8a522b5efe4885ae8a4774390410a1edac03399db23cca2d5624e3c` | 条件可独立理解；评审答案对应 |
| `CO-DATA-001` | `6ec0105f9d865cdb7ace90076ae09eced18f2dca48e02b4f81f0de9b2b7f8b4a` | 条件可独立理解；评审答案对应 |
| `CO-DATA-002` | `aad4822b5c9469b92003e16e3e92c4936f5f886e0d157548c6c576c66be49e7e` | 条件可独立理解；评审答案对应 |
| `CO-IO-001` | `baf00b03db7129a27d9d0e441f81cb7517369884742e5a8a212f58f16dd87200` | 条件可独立理解；评审答案对应 |
| `CO-IO-002` | `5b2ab2cf6a7a943c927afc8a11b132747ccf011e434c3041c99e09e3a19bd4c6` | 条件可独立理解；评审答案对应 |
| `CO-IO-003` | `3338de982c86bbbef838675b30d4fc36422d49c9c4a9017211725051fdccbd49` | 条件可独立理解；评审答案对应 |
| `CO-ISA-001` | `bc45450a71594732e60e37e7e2a7fc9a7be47bca7ef4ae0e39ac45d4449398d6` | 条件可独立理解；评审答案对应 |
| `CO-MEM-001` | `2dd9e212126a8633f2c601a88ba76508a4e765021f6dd3356b73c70ae0f26e8a` | 条件可独立理解；评审答案对应 |
| `CO-PERF-001` | `c1003b59b91809fcb73ba93e9f035241dc01114347a9141de2b2acde1c377a72` | 条件可独立理解；评审答案对应 |
| `CO-PIPE-001` | `1c0c6b3bec4295a6d0ff2ab809176dd083a845fcf6540b1e843d7c08e330fdeb` | 条件可独立理解；评审答案对应 |
| `DS-ALG-001` | `7da66dba6d80772859a87297f2bed80617c590f54566179fa97bbfb2c17eebd3` | 条件可独立理解；评审答案对应 |
| `DS-ARRAY-001` | `d86898e837b47d76a26743c72320cfd1bb1dc10d5bdb923f9f4203e1a64268cd` | 条件可独立理解；评审答案对应 |
| `DS-GRAPH-001` | `2dd0bf62013d55b8f6f9389f46c57e3b609055c504879c9868ff6df1f970481e` | 条件可独立理解；评审答案对应 |
| `DS-GRAPH-002` | `f274b5e4e430fe225ad74ff6668778e6d69685b2785478d39acc6a1d7e63c557` | 条件可独立理解；评审答案对应 |
| `DS-GRAPH-003` | `305194bc130d5c124f005f968c590de4623d03e814e1406fbae2e5effc638d7e` | 条件可独立理解；评审答案对应 |
| `DS-GRAPH-004` | `febd81134af8acbb09b905dbfa14d7f316ed03eb86ad3cb137520b44ce4100af` | 条件可独立理解；评审答案对应 |
| `DS-LIST-001` | `8ce92649b6bcfa610a5fd30fb4f4526acfc84dba72c23925c10d4d3b264aaf70` | 条件可独立理解；评审答案对应 |
| `DS-QUEUE-001` | `991b0859aa142aa713a53cfadf3538a25976e2c0a4e41ebf123756c20af20af9` | 条件可独立理解；评审答案对应 |
| `DS-SEARCH-001` | `da92e5268d33144e7ede992e85459569862f69296fccaa391b6cc64798d06b9d` | 条件可独立理解；评审答案对应 |
| `DS-SEARCH-002` | `f98202c75310a71aea7fd92541ca3e4a9e2023c2ba06e093a085106db7dad39a` | 条件可独立理解；评审答案对应 |
| `DS-SEARCH-003` | `22fe207728222ab476cdfc341124dc8c7459f85c0b2090d63c737bcfc3692a7b` | 条件可独立理解；评审答案对应 |
| `DS-SORT-001` | `8f803b120b37acc8d5e6f53d45b8c68698f55b4bb444aba926fa4005029dc231` | 条件可独立理解；评审答案对应 |
| `DS-STACK-001` | `f2e0f849f32cdb38b707f284dea12ed0671d8b858889e979c236e82b60f24626` | 条件可独立理解；评审答案对应 |
| `DS-TREE-001` | `85a42e87c3033cfc89b308966d35fec9f72a6fc1cdf5c744a545626ca4b5aefe` | 条件可独立理解；评审答案对应 |
| `DS-TREE-002` | `c70b6495aab7f12e883cb3ec587cf51d85b5c7d4d5792b16c76f29aeb294ddda` | 条件可独立理解；评审答案对应 |

## CO-CACHE-002 串行模型与来源复审（2026-10-31）

本次受审卡 SHA-256：`7743df6e7b759b2633a8a98c3fd7d2a9273cd52074e132d1646287a30b75de55`。题设每次先花 1 ns 查 Cache，缺失概率 5%，缺失再额外花 20 ns 且无重叠，因此命中耗 1 ns、缺失耗 21 ns；按概率加权为 0.95×1+0.05×21=2 ns，解析结果正确。仅证明该题设模型下的算术，不证明所有系统均串行或无重叠。

来源 [Cornell Caches](https://www.cs.cornell.edu/courses/cs3410/2026sp/notes/caches.html) 的实际标题为 **Handling Stores**，其中讨论写直达、写回和脏位替换；卡中写的定位 “Write Policies” 在该页面未找到，应改成实际标题以便复核。“Larger Blocks” 并非该卡写策略论据，建议移除。该页不证明本题给定数值和所有写缓冲完成时机；卡片的范围限制没有扩大成全卡已核。此定位问题未在本报告中修改卡片，修正后需要重新绑定哈希。

## 自测与来源细化后的定向复审（2026-10-31）

DS-SEARCH-002：闭区间 [9,20] 从 3、8、12、18、22 中选出 12、18；评审答案正确，旧例题未给出此题答案。CO-MEM-001：16/4 = 4 片位扩展，8K/1K = 8 组字扩展，共 32 片；评审答案正确，旧例题未给出此题答案。两题均包含必要题设。

CO-CACHE-001 定位 Larger Blocks，CO-CACHE-002 定位 Handling Stores，均与此前实际阅读的相应内容一致。CO-ALU-001、CO-DATA-001 限于性能课件 PDF 第5页补码示例，CO-PERF-001 限于第16页 CPI 关系，CO-BUS-001 限于 OSTEP §36.1 的背景并保留仲裁和带宽待核。来源均只证明所列部分，不证明完整卡片。

| ID | 本次 SHA-256 |
| --- | --- |
| `DS-SEARCH-002` | `542b79b0c6c36160dfea5cbe56883d709f0c11a5d227de39e8e179e60f8ad3f3` |
| `CO-MEM-001` | `9c9a76af5bcb1d912b16821b9065b1056a7844e6fba99be4465d35669747b1ce` |
| `CO-CACHE-001` | `91a85a918c5547a611190f189140031ebaeb0b3416dc1adca3ae92b9f1522c49` |
| `CO-CACHE-002` | `65a5293e0d4598418f01c707eb4fc575c61a5571cfa2dd6eb14a9c861179b0e1` |
| `CO-ALU-001` | `57dbeb45650a50de46630cf658a8ece604208cc82f79061cd82acaa1c0a13044` |
| `CO-DATA-001` | `7d2305125104960b6bbbf41ed231c7fd0893d117680581f4731b4762cae7eba7` |
| `CO-PERF-001` | `a02ec62a426e43b04d23d76f0ef50631f21aa2b29cab5c7fba5c283c00e2d834` |
| `CO-BUS-001` | `4e9f407239dbbf2e47ea667b7ea955fdd0f5ebb730b1f39067e9073e12098b48` |

本表取代同一文件此前对应哈希用于本次定向复核，历史记录不删除。其他卡片是否保持不变应另行比较。
