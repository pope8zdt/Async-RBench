**[Question 1] - What is the problem?**
Can a plain non-hierarchical visual Mamba remain spatially continuous and resolution-flexible when tokens are dynamically pruned for efficient dense prediction?

**[Question 2] - Why is it interesting and important?**
Plain encoders are easier to reuse in systems such as SAM, DINOv2, CLIP, and LLaVA, but practical deployment also needs lower token cost. Preserving 2D state continuity during pruning could make one simple encoder useful across classification, segmentation, and detection.

**[Question 3] - Why is it hard?**
Mamba makes B, C, and Delta token dependent, so removing a token changes both the scan path and the hidden-state dynamics. Raster or bidirectional shortcuts can introduce spatial jumps, and a policy learned at one resolution may break adjacency or calibration at another.

**[Question 4] - Why hasn't it been solved before?**
ViM and VMamba study scan organization, while PlainMamba emphasizes continuous 2D scanning; pruning work usually treats tokens as transformer units rather than state-transition links. These lines do not jointly constrain topology, hidden-state alignment, and resolution transfer.

**[Question 5] - What are the key components of my approach and results?**
TopoScan-Mamba uses a resolution-flexible continuous 2D scan, pruning-aware hidden-state alignment, and calibrated token-importance gates that reconnect only spatial neighbors. We evaluate ImageNet-1K, ADE20K, and COCO using top-1 accuracy, mIoU, AP, FLOPs, latency, and scan-discontinuity rate; expected results retain dense-task quality while reducing compute and eliminating pruning-induced scan jumps.
