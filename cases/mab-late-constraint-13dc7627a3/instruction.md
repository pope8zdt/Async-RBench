Dear Research Team,

            You are collaborating to generate a new research idea based on the following Introduction:

            **Introduction**

             Introduction
Deep learning practitioners commonly regard recurrent ar-
chitectures as the default starting point for sequence model-
ing tasks. The sequence modeling chapter in the canonical
textbook on deep learning is titled “Sequence Modeling:
Recurrent and Recursive Nets” (Goodfellow et al., 2016),
capturing the common association of sequence modeling
and recurrent architectures. A well-regarded recent online
course on “Sequence Models” focuses exclusively on recur-
rent architectures (Ng, 2018).
1Machine Learning Department, Carnegie Mellon Univer-
sity, Pittsburgh, PA, USA2Computer Science Department,
Carnegie Mellon University, Pittsburgh, PA, USA3Intel Labs,
Santa Clara, CA, USA. Correspondence to: Shaojie Bai
<shaojieb@cs.cmu.edu >, J. Zico Kolter <zkolter@cs.cmu.edu >,
Vladlen Koltun <vkoltun@gmail.edu >.On the other hand, recent research indicates that certain con-
volutional architectures can reach state-of-the-art accuracy
in audio synthesis, word-level language modeling, and ma-
chine translation (van den Oord et al., 2016; Kalchbrenner
et al., 2016; Dauphin et al., 2017; Gehring et al., 2017a;b).
This raises the question of whether these successes of con-
volutional sequence modeling are conﬁned to speciﬁc ap-
plication domains or whether a broader reconsideration of
the association between sequence processing and recurrent
networks is in order.
We address this question by conducting a systematic empiri-
cal evaluation of convolutional and recurrent architectures
on a broad range of sequence modeling tasks. We specif-
ically target a comprehensive set of tasks that have been
repeatedly used to compare the effectiveness of different
recurrent network architectures. These tasks include poly-
phonic music modeling, word- and character-level language
modeling, as well as synthetic stress tests that had been de-
liberately designed and frequently used to benchmark RNNs.
Our evaluation is thus set up to compare convolutional and
recurrent approaches to sequence modeling on the recurrent
networks’ “home turf”.
To represent convolutional networks, we describe a generic
temporal convolutional network (TCN) architecture that is
applied across all tasks. This architecture is informed by
recent research, but is deliberately kept simple, combining
some of the best practices of modern convolutional archi-
tectures. It is compared to canonical recurrent architectures
such as LSTMs and GRUs.
The Background
Convolutional networks (LeCun et al., 1989) have been
applied to sequences for decades (Sejnowski & Rosen-
berg, 1987; Hinton, 1989). They were used prominently
for speech recognition in the 80s and 90s (Waibel et al.,
1989; Bottou et al., 1990). ConvNets were subsequently
applied to NLP tasks such as part-of-speech tagging and
semantic role labelling (Collobert & Weston, 2008; Col-
lobert et al., 2011; dos Santos & Zadrozny, 2014). More
recently, convolutional networks were applied to sentence
classiﬁcation (Kalchbrenner et al., 2014; Kim, 2014) and
document classiﬁcation (Zhang et al., 2015; Conneau et al.,
2017; Johnson & Zhang, 2015; 2017). Particularly inspiring
for our work are the recent applications of convolutional
architectures to machine translation (Kalchbrenner et al.,
2016; Gehring et al., 2017a;b), audio synthesis (van den
Oord et al., 2016), and language modeling (Dauphin et al.,
2017).
Recurrent networks are dedicated sequence models that
maintain a vector of hidden activations that are propagated
through time (Elman, 1990; Werbos, 1990; Graves, 2012).
This family of architectures has gained tremendous pop-
ularity due to prominent applications to language mod-
eling (Sutskever et al., 2011; Graves, 2013; Hermans &
Schrauwen, 2013) and machine translation (Sutskever et al.,
2014; Bahdanau et al., 2015). The intuitive appeal of re-
current modeling is that the hidden state can act as a rep-
resentation of everything that has been seen so far in the
sequence. Basic RNN architectures are notoriously difﬁcult
to train (Bengio et al., 1994; Pascanu et al.,

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
Produce the required five-question proposal building on the broad TCN-versus-RNN sequence comparison. Three workstreams preserve recurrent baselines, temporal convolutional receptive fields, and diverse sequence tasks. A fourth evaluator-owned scope delta adds streaming latency, peak-memory, and effective-history budgets. Selectively revise the proposal with streaming data, accuracy/latency/memory metrics, controlled receptive-field ablations, and expected trade-offs.
