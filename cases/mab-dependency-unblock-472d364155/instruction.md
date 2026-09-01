Dear Research Team,

            You are collaborating to generate a new research idea based on the following Introduction:

            **Introduction**

             

1 Introduction

Humans use all facial expressions, body motions, and hand motions to express our emotions and intentions, and interact with other people and objects.
In particular, facial expressions and hand gestures are one of the most powerful channels for non-verbal communication, and hand motions are necessary to interact with diverse types of objects.
Modeling the facial expression, body motion, and hand motion altogether is extremely challenging.
Several whole-body 3D human geometry models have been introduced [21, 37, 50, 2].
Among them, SMPL-X [37] is the most widely used one, which motivated a number of 3D whole-body pose estimation methods [9, 45, 11, 32, 52, 26, 28, 4] and benchmarks [36].


To represent 3D humans beyond the minimally clothed parametric models, personalized 3D human avatars have been recently studied.
The 3D human avatar is a representation that combines 3D geometry and the appearance of a certain person, which can be animated and rendered with novel poses.
However, most of existing 3D human avatars [39, 38, 25, 8, 6, 20, 15, 19, 24, 18] modeled from a casually captured video only support body motions without facial expressions and hand motions.
Their avatars bake facial expressions and hand poses, and animating them is not possible.
A recent work [47] introduced a whole-body avatar that supports animation with facial expressions, and body and hand poses; however, it requires 3D observations, such as 3D scans or RGBD images with highly accurate SMPL-X registrations, with diverse poses and facial expressions.
Such an assumption does not hold for the majority of casually captured videos in daily life.


Figure 1: 
From (a) a monocular video from a single person, we create our (b) ExAvatar, an expressive whole-body 3D avatar, animatable with novel facial expression code, hand poses, and body poses of SMPL-X.



We present ExAvatar, an expressive whole-body 3D human avatar that can be made from a short monocular video.
ExAvatar is designed as a combination of the whole-body 3D parametric model (SMPL-X) [37] and 3D Gaussian Splatting (3DGS) [22].
It utilizes the whole-body drivability of SMPL-X and the photorealistic and efficient rendering capability of 3DGS.
After the training, it is animatable with novel facial expression code and 3D pose of SMPL-X, as shown in Fig. 1.
Despite its desired properties, modeling ExAvatar is an non-trivial task with the following two challenges: 1) a limited diversity of facial expressions and poses in the video and 2) the absence of 3D observations, such as 3D scans and RGBD videos.
The limited diversity in the video makes a drivability with novel facial expressions and poses non-trivial.
In addition, the absence of 3D observations creates ambiguity in the occluded human parts, exhibiting noticeable artifacts in novel facial expressions and poses.


To address them, we propose a novel hybrid representation of the surface mesh and 3D Gaussians in ExAvatar.
Our hybrid representation treats each 3D Gaussian as a vertex on the surface, where the vertices have pre-defined connectivity (i.e., triangle faces) between them following the mesh topology of SMPL-X.
Existing volumetric avatars [39, 38, 25, 8, 6, 20, 15, 19, 47] do not have the connectivity by the definition.
Also, previous 3DGS-based [24, 18] works consider a set of 3D Gaussian points as a point cloud without considering the connectivity between them.


Using our hybrid representation, our

            **Your Task**

            1. **Literature Review**: Analyze the Introduction provided and conduct a brief literature review to understand the current state of research in this area.

            2. **Brainstorming**: Collaboratively brainstorm potential research ideas that build upon or address gaps in the Introduction.

            3. **Summarization**: Summarize your collective ideas.

            4. **Formulate a New Research Idea**: Develop a new research proposal in the format of the '5q', defined below:

               **Here is a high-level summarized insight of a research field Machine Learning.**

               **Here are the five core questions:**

               **[Question 1] - What is the problem?**

               Formulate the specific research question you aim to address. Only output one question and do not include any more information.

               **[Question 2] - Why is it interesting and important?**

               Explain the broader implications of solving this problem for the research community.
               Discuss how such a paper will affect future research.
               Discuss how addressing this question could advance knowledge or lead to practical applications.

               **[Question 3] - Why is it hard?**

               Discuss the challenges and complexities involved in solving this problem.
               Explain why naive or straightforward approaches may fail.
               Identify any technical, theoretical, or practical obstacles that need to be overcome. MAKE IT CLEAR.

               **[Question 4] - Why hasn't it been solved before?**

               Identify gaps or limitations in previous research or existing solutions.
               Discuss any barriers that have prevented this problem from being solved until now.
               Explain how your approach differs from or improves upon prior work. MAKE IT CLEAR.

               **[Question 5] - What are the key components of my approach and results?**

               Outline your proposed methodology in detail, including the method, dataset, and metrics that you plan to use.
               Describe the expected outcomes. MAKE IT CLEAR.

            Please work together to produce the '5q' for your proposed research idea.

            Good luck!

You should answer the task in the fllowing format:
                **[Question 1] - What is the problem?**

                Formulate the specific research question you aim to address. Only output one question and do not include any more information.

                **[Question 2] - Why is it interesting and important?**

                Explain the broader implications of solving this problem for the research community.
                Discuss how such a paper will affect future research.
                Discuss how addressing this question could advance knowledge or lead to practical applications.

                **[Question 3] - Why is it hard?**

                Discuss the challenges and complexities involved in solving this problem.
                Explain why naive or straightforward approaches may fail.
                Identify any technical, theoretical, or practical obstacles that need to be overcome. MAKE IT CLEAR.

                **[Question 4] - Why hasn't it been solved before?**

                Identify gaps or limitations in previous research or existing solutions.
                Discuss any barriers that have prevented this problem from being solved until now.
                Explain how your approach differs from or improves upon prior work. MAKE IT CLEAR.

                **[Question 5] - What are the key components of my approach and results?**

                Outline your proposed methodology in detail, including the method, dataset, and metrics that you plan to use.
                Describe the expected outcomes. MAKE IT CLEAR.

ASYNC-RBENCH EXTENSION
The harness then delivers evaluator-owned asynchronous authority through the private event channel.
Produce the required five-question proposal for expressive whole-body avatars from short monocular video. Three workstreams preserve the SMPL-X/3DGS representation, limited-pose problem, and occlusion ambiguity. A fourth evaluator-owned benchmark arrives later. Integrate expression, hand, body, occlusion, and novel-pose coverage, with concrete data, geometry/rendering metrics, ablations, and expected outcomes.
