# Assignment

## Take-home brief

## The task

Companies moving off older ETL tools such as Informatica PowerCenter have hundreds of scheduled workflows. Before we migrate one, we need to know how often it runs, because that decides how it is migrated and checked. The customer's run-history export is usually incomplete. Use one rule: a workflow is in scope if it runs hourly or less often, and anything faster, or whose frequency cannot be worked out, goes to an engineer.

We send you [run_history.csv](https://drive.google.com/file/d/10WwroK3Hlz6t-uGgzxs6BH_Hd2jWl-Yx/view?usp=sharing) (one row per run for about 40 workflows over 90 days) and [feedback.md](https://drive.google.com/file/d/124kADuNWQEjBcQufSQFFkwUwNRV-77W3/view?usp=sharing) (six messages from current users). All data is synthetic.

## What to submit

Please submit **a repository or zipped folder** with:

1. A one-page spec for this step, with a definition of done and at least three examples of good and bad output.
2. A working prototype that reads the CSV, shows each workflow's frequency and scope decision, and lets a user correct a decision.
3. The prompts or AI conversations you used, and how long you spent.
4. A short README: how to run it, what you assumed and left out, where your logic is most likely wrong, and where an AI tool got something wrong.

## Using coding agents

We expect you to use AI tools such as Claude, ChatGPT/Codex or Cursor.
