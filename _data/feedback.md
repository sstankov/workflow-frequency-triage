# Feedback on the run-frequency step

Six messages from people who use Flowline today, about the current step that works out how often each workflow runs and whether it is in scope. They came in through Slack, the Flowline Forum, email and a support ticket. Names are removed and all data is synthetic. The workflow names refer to `run_history.csv`.

## 1. Forward deployed engineer, Slack #flowline-product-support, 22 Sep

> The scope step flagged wf_SLS_ORDERS_INCR as running every 49 minutes and sent it to the engineer queue. It's a daily job. The short gaps are manual re-runs after it failed. Same thing happened with wf_INV_STOCK_HOURLY. A failed run and its re-run are one run of the schedule, not two.

## 2. Forward deployed engineer, Slack #flowline-product-support, 24 Sep

> Most of the "too frequent" list on this estate only has three days of history, because their repository purges logs for busy workflows after three days. The customer keeps asking why we can't scope them. Can we wait until we have 90 days of history for everything before we decide?

## 3. Consulting engineer, Flowline Forum notes, 29 Sep

> Some of the frequency numbers feel off. Mostly the finance jobs, I think. A chart would help.

## 4. Data platform lead at a client, email, 1 Oct

> Your report put wf_PAY_AUTH_HOURLY in scope as an hourly job. It isn't hourly, it runs every half hour through the morning. Please don't go by the names, half of ours are out of date.
>
> Separately, some workflows haven't run for weeks, for example wf_MKT_CAMPAIGNS. We'd rather switch those off than pay to migrate them. Can the report show which ones look retired?

## 5. Forward deployed engineer lead, Slack #flowline-dev, 2 Oct

> Month-end and quarterly jobs keep landing in "unknown" because there are only one to three runs in a 90-day export. On the last estate that created 14 engineer tickets, and all but one were plain monthly jobs. Three runs on the last day of three consecutive months is a monthly job. Only send things to engineers when we really can't tell.

## 6. Operations engineer at a client, support ticket, 5 Oct

> Two problems with our export. First, the upload rejected rows for aborted runs because end_time is empty. That's how PowerCenter writes them, so please accept them. Second, wf_WEB_CLICKS runs every hour but the tool says "too frequent", because some runs start 52 minutes apart. It's hourly and we need it in the first wave.
