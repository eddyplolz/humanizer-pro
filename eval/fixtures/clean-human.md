# Clean Human Control

We moved the importer into the nightly job because the old request path kept timing out during signup
spikes. It is less elegant, but it means support can rerun a failed batch without asking engineering to
dig through logs at midnight. I would rather have the boring button that works than a clever endpoint
that only behaves when traffic is polite.
