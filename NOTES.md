
### Publication lag
Measured load arrives roughly 2 hours behind real time. At prediction time the
most recent measurement available is therefore ~2 h old. Lag features must
respect this offset; short lags that exist in the training table are not
available in production.
