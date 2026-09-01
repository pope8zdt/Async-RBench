**[Question 1] - What is the problem?**
How can a hierarchical table-tennis robot adapt its skill selection to a previously unseen human opponent while accounting for execution uncertainty and preserving real-time safety?

**[Question 2] - Why is it interesting and important?**
Competitive table tennis couples strategic choice with high-speed physical execution, so success would advance robots that must adapt safely to unfamiliar humans in dynamic environments. Explicit uncertainty could also make modular robot policies more transparent and reusable.

**[Question 3] - Why is it hard?**
Ball position, speed, and spin change within milliseconds; opponent evidence is initially sparse; and the strategically best shot may exceed a low-level skill's reliable operating region. Greedy win-rate selection can over-trust an uncertain skill, while conservative control can fail to adapt quickly enough.

**[Question 4] - Why hasn't it been solved before?**
Prior systems address returns, targets, smashes, rallies, or known training partners, and hierarchical systems record skill descriptors without jointly calibrating them under online opponent shift. Existing adaptation methods rarely connect confidence, physical feasibility, and strategic regret in a full unseen-human game.

**[Question 5] - What are the key components of my approach and results?**
We propose risk-calibrated hierarchical skill selection with online opponent adaptation and confidence-aware fallback. Low-level forehand, backhand, serve, targeting, and spin skills expose calibrated descriptors to a high-level controller that updates an opponent model and selects a safe fallback when execution confidence is low. We evaluate held-out unseen-human match trajectories, spin- and velocity-stratified robot table-tennis trials, and simulation-to-real skill rollouts using point win rate, return success rate, target error, decision latency, calibration error, safety constraint violations, and adaptation regret; expected results improve rapid adaptation without sacrificing physical safety.
