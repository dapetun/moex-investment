## Cursor Cloud specific instructions

Single Streamlit app (`app.py`) plus the `moex_portfolio` library. No database, Docker, or other services. Install, test, and run commands are in `README.md` and `.github/workflows/ci.yml`.

- Packages install with `pip install --user` into `~/.local`. `streamlit`, `pytest`, `ruff`, and `bandit` are on `~/.local/bin`, which is not on the default non-interactive `PATH`. `~/.bashrc` prepends that directory. If a shell cannot see them, `export PATH="$HOME/.local/bin:$PATH"`. `python3 -m pytest` and `python3 -m streamlit` work without that export.
- Set `MPLBACKEND=Agg` before pytest (same as CI) so matplotlib does not look for a display.
- Dev server: `streamlit run app.py --server.headless true --server.port 8501`. `--server.headless true` skips Streamlit's first-run email prompt. Leave the process running.
- **Run Optimization** always calls MOEX ISS `get_all_shares()` before the CSV cache. Cache freshness is the file mtime (`DEFAULTS.cache_max_age_hours`, 24h), not the last date inside `data/price_data.csv`. A fresh checkout therefore looks fresh even when the last row is older. The default risk-free source is CBR; if `cbr.ru` is unreachable the sidebar falls back to 16% and the page still loads.
- That button also runs dividends, fundamentals, the OFZ list, IMOEX history, and the default walk-forward ML tab in the same script pass. A successful run is typically under a minute when ISS responds; slow APIs stretch it.
