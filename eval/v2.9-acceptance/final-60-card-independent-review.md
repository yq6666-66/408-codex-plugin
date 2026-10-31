# 60 张知识卡冻结树独立审查

逐卡 SHA-256 和机器可读判定见 final-60-card-independent-review.json。该审查检查自测题条件和例题解答直接给出同题答案；概念对通用规则的教学说明不自动认定为泄题。数字替换类同构练习不自动判为泄题，但也不等于高质量迁移测试。

## 问题

1. DS-SEARCH-002：例题已给出下界以上不存在键时返回空，自测的同一区间结果由此直接给出；是否必须扫描全部叶是额外问题。
2. CO-MEM-001：例题已经给出1K×4两片并行构成1K×8，自测问的正是该结论。
3. OS-SCHED-001：5单位任务、时间片2的题面，完成前经历几片可理解为2个完整片或包含最后不满片的3次分配，须明确口径。
4. OS-BASIC-001：自测题已给出“同步触发异常”，又要求区分同步异常或外部中断，答案在题干内；这影响练习质量，不属于例题泄题。

## DS/CO 来源状态

30 张均逐项检查了状态、来源及限定范围；DS-LIST-001、DS-TREE-001、CO-BUS-001 均明确仅相关背景，主要规则待核。DS-ALG-001、CO-CPU-002、CO-MEM-001 无已读一手来源，保持待核。CO-CACHE-001 的 Larger Blocks 和 CO-CACHE-002 的 Handling Stores 均可在来源正文定位；前者限制写缓冲是与地址划分无关的赘述。其余有引用项仅按各卡具体范围与限制理解。

| ID | SHA-256 | 自测 | DS/CO 来源 |
|---|---|---|---|
| CN-APP-001 | 8249309e3869376b0ae8bd302a146dada2e649ae054d62a28f19b1faf236ddba | pass | 不在本轮DS/CO来源范围 |
| CN-ARCH-001 | 25945bb406d1e5e837af683f86bf495e5ef1a2542a48c92971b410751cff8e8a | pass | 不在本轮DS/CO来源范围 |
| CN-ARQ-001 | 5b6a8ffa41afc5096347cb103b45e965983f50169c7924051e2a4e583c6e8259 | pass | 不在本轮DS/CO来源范围 |
| CN-LAN-001 | 15a3483654728759145b4fcd6d045673af4ef3fabfa1d63228a93b4d6aae6ea2 | pass | 不在本轮DS/CO来源范围 |
| CN-LINK-001 | 38f73649d54180b695280534fc85dacc8255429f8e8d33bc3143596386bc1bb7 | pass | 不在本轮DS/CO来源范围 |
| CN-MAC-001 | ccc67bf6937f95285f2c0cbc2407237806243efc329c240c49d3a76355e00bae | pass | 不在本轮DS/CO来源范围 |
| CN-NET-001 | cf086a2ec1605508341c0bb2c61f362b307de311d662105e949026367ff57c75 | pass | 不在本轮DS/CO来源范围 |
| CN-NET-002 | 2466eb25f11317d64607dd9f9ba1ad6da3335a9265d1f9cd1f1838c224e5bb04 | pass | 不在本轮DS/CO来源范围 |
| CN-NET-003 | be1560ede999f810667586e3be6d2bdd6fbe7fec532a0a45109661662493ab53 | pass | 不在本轮DS/CO来源范围 |
| CN-PERF-001 | 1eec3fae8f5a5d1e5425ff5307a9b2369763f175885839d0f89ba7d0936317be | pass | 不在本轮DS/CO来源范围 |
| CN-PHY-001 | dbacced1b1220136801f7c61b88cdafe44bada3c5c01000354044044dad2ed28 | pass | 不在本轮DS/CO来源范围 |
| CN-ROUTE-001 | 9edce60728303031c71017a9251edeb019bd9578e2d234fbf6a09ac0f1582dbb | pass | 不在本轮DS/CO来源范围 |
| CN-TCP-001 | 034c5ac6829969e901c444160757d95abfc9c2373cf60b60ae956b60fea59efc | pass | 不在本轮DS/CO来源范围 |
| CN-TCP-002 | fc3387b59d0fde550bf177da46bb6c68a28c54832255e91a243337e36c08dbc0 | pass | 不在本轮DS/CO来源范围 |
| CN-TRANS-001 | b86585ee4e3c7966af687c006d1f2898a4b8d49f491ec759c6fd3646f9187d81 | pass | 不在本轮DS/CO来源范围 |
| CO-ALU-001 | cca95b148af70e57beba7b1dec956d330242992087cf92b9a64d94a2f79ac423 | pass | partial-support |
| CO-BUS-001 | e9127764853dd02f969ab4de1efe9bc7a4321993052729dd608239137eff070b | pass | background-only |
| CO-CACHE-001 | 91a85a918c5547a611190f189140031ebaeb0b3416dc1adca3ae92b9f1522c49 | pass | partial-support |
| CO-CACHE-002 | 65a5293e0d4598418f01c707eb4fc575c61a5571cfa2dd6eb14a9c861179b0e1 | pass | partial-support |
| CO-CPU-001 | 43a79fb2a110ddaadc950d9fb69d76527e726e0fcaed9f87c9c221570c4984cf | pass | partial-support |
| CO-CPU-002 | 44d9a12600d4fc1544d4a80dcb95b633aa2bcadca4f59eb866f790edb5e5e11d | pass | pending |
| CO-DATA-001 | cca54583460f99e37c9b38ec5c3f7ea99e46204bcd615c7fe49d755cf7410e7a | pass | partial-support |
| CO-DATA-002 | 7e6e71646978fe02b37fbe9d731f71bda7fe69a913e397f687cbdaa78b2442a8 | pass | partial-support |
| CO-IO-001 | f9b45a050db9fe338302f7d459e040ad626498ae794df04f31eaf59ee1f1fe43 | pass | partial-support |
| CO-IO-002 | dee1bd595e89a39583bab25983f50df3faaae5ab59f7970650d73b671d0fae62 | pass | partial-support |
| CO-IO-003 | 5ef4f655b2c86355b841ea4e2e3d0cce7f6e17ea44dfe2220f3708fa4b322070 | pass | partial-support |
| CO-ISA-001 | b759e31c6cb7e6ac8215e451baa050a4afad31264c6c30f5e23c83c35767a993 | pass | partial-support |
| CO-MEM-001 | f518844765801b8b8e847dd27461d24d38da778bf52f89edff9e876c990832e9 | direct-disclosure | pending |
| CO-PERF-001 | 7e763a29e6ebe4c530b3d972f2e1f5ea5dde9ead4028dbb396597b89cf18f5c5 | pass | partial-support |
| CO-PIPE-001 | 5e2295ec6535f336bd4d6814eabf18f058c003ad19b203edfffe30922cd7068e | pass | partial-support |
| DS-ALG-001 | 4cc6df5090b4a90546c161bf18caf9f87b6360486b512a7809164a3031ec99a6 | pass | pending |
| DS-ARRAY-001 | 17308ce7c0cc232fd1d4da1233fbfbc4cc431223aa0ee709f6b42b35422a718a | pass | partial-support |
| DS-GRAPH-001 | c066c839c981802b1b13d64e812a343be631910085171ada56b23aa8e57132ca | pass | partial-support |
| DS-GRAPH-002 | cd14a8bc1f6ace57c5edaf1e5094f7a86922deca3f213d730bc130baa2c8d6bf | pass | partial-support |
| DS-GRAPH-003 | 99361a4c6222b6a0f8a5025f482bb371af3297f9f8d5a6f2068d825e7046cb49 | pass | partial-support |
| DS-GRAPH-004 | fb70aa3a91f7fbaf00d3392537f72bd8fbd35b736c5a9455493861dc036052b7 | pass | partial-support |
| DS-LIST-001 | 2ca0ead802406dc2d1d065453b7601d0101e90c6c3be1d9a12d5ec408bd4454d | pass | background-only |
| DS-QUEUE-001 | 81c7a0b0654ef8cc275fcbe8b1d4636e833cc5beece2b7fdefb91c1d5bc8792c | pass | partial-support |
| DS-SEARCH-001 | a5e356e5186f81d741cd7ca9b63be883a8ae7d1df8f73ecf529dc0e8ee84db70 | pass | partial-support |
| DS-SEARCH-002 | 82d098f998af46311447de896af4f314d689ee5f8dbc98ce68ef43f0b2f5d35f | partial-disclosure | partial-support |
| DS-SEARCH-003 | e1968ed767da23b987fe0b77c38c644b83a683f885e87e34be1a2c2e0ae85907 | pass | partial-support |
| DS-SORT-001 | 81adb74f03692e711defafcd39af6bc3d2598348a8995dceb23cfba845cc8473 | pass | partial-support |
| DS-STACK-001 | fe00bc2a775710cf8478d55e267dbf375299ec39293b1c84fc10a269122471b9 | pass | partial-support |
| DS-TREE-001 | db1879f3eafda7458107928f5c7bf2d0ea382ea936e7a15c8f15db9e9c64fac7 | pass | background-only |
| DS-TREE-002 | 4fd7748c6e1d8ffc3618d7a29612d3dc25036f907f7aa801da32429b21067929 | pass | partial-support |
| OS-BASIC-001 | aa3029250824ad6082f587e2a19b788a82cd9a180312f4b6415db49e49c86d88 | weak-assessment | 不在本轮DS/CO来源范围 |
| OS-DEAD-001 | 4150ec2fef71a8858221a28f1ef67b8243046540decf7678d40451b95ee898e1 | pass | 不在本轮DS/CO来源范围 |
| OS-DISK-001 | 074be31e377589fc16b5b7f5b07429f1c4c9a06597708e72452c7ac7cd2bfd8a | pass | 不在本轮DS/CO来源范围 |
| OS-FILE-001 | 6deee5f55262a8b9167c5f8e1e9a1b163b14260cd011168a4141a3be966dcdf6 | pass | 不在本轮DS/CO来源范围 |
| OS-MEM-001 | c696f36baa87413a79eaf8960148a6876608841108b62032d941262e9b3234c3 | pass | 不在本轮DS/CO来源范围 |
| OS-MEM-002 | 2c8a3c405566b73a6ad4daf8c2f5ed3729b59e158cea259cd07679b5311c05a4 | pass | 不在本轮DS/CO来源范围 |
| OS-MEM-003 | 4eeb42d69038530511f1da4f07db96a89bbf955ce675a1488ca25bcedf2716ee | pass | 不在本轮DS/CO来源范围 |
| OS-MEM-004 | 915c8a5d9d141450c5ebc8165ab123381a51002b90085900c138b1b9908a6831 | pass | 不在本轮DS/CO来源范围 |
| OS-MEM-005 | a6ee3f032a3552b10d7e951ea72f9aa8ec7880835f6f3b03547509feb23d54ca | pass | 不在本轮DS/CO来源范围 |
| OS-PROC-001 | 29b4dd8f525c3e07fdbf6da6fce561eef75f19189356bd79d7f813b735b7e383 | pass | 不在本轮DS/CO来源范围 |
| OS-PROC-002 | d3f34bf308e98d73619e18fb8a7a8c0d244b8f7acecc58fcf7815ac6981837cb | pass | 不在本轮DS/CO来源范围 |
| OS-SCHED-001 | 0ddcf2211c2f8c250c2e88ee29480eaf3a2aced9f65358449e063a4556ca656b | ambiguous | 不在本轮DS/CO来源范围 |
| OS-SCHED-002 | 6f97f7e8b96b53c0023973078f90aa96baedd7f7dc3d0c043a096bd691c86699 | pass | 不在本轮DS/CO来源范围 |
| OS-SYNC-001 | 1c8133004d336aff29b6f189dda7e1123d14ea0aeb29b747567228c56335e6fc | pass | 不在本轮DS/CO来源范围 |
| OS-SYNC-002 | 3bb906da7993c7733292b656a1770e6ff01e2f385aebf6b46ca9b3aa52479740 | pass | 不在本轮DS/CO来源范围 |

本报告不修改卡片。任何内容、来源或换行变更后须重新绑定哈希并复核受影响项。
