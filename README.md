# 📖 README.md

## OtoProxy 🚀

**OtoProxy** is an automated proxy scraper and checker designed to collect and verify HTTP, SOCKS4, and SOCKS5 proxies. Built for speed and efficiency, it runs on GitHub Actions every 6 hours, saving valid proxies to categorized files and maintaining a blacklist for invalid ones. This project is inspired by and partially based on code from [Omar-Obando/proxystorm-fastest-proxy-scraper-checker](https://github.com/Omar-Obando/proxystorm-fastest-proxy-scraper-checker.git). A huge thanks to **Grok AI** by xAI for assisting in refining and optimizing the codebase! 🙌

### ✨ Features
- 🌐 Scrapes proxies from URLs listed in `sites.txt` (HTTP, SOCKS4, SOCKS5).
- ✅ Verifies proxies with a 1500ms latency limit.
- 💾 Saves valid proxies to:
  - `all-proxies.txt` (all types)
  - `http-proxies.txt` (HTTP only)
  - `socks4-proxies.txt` (SOCKS4 only)
  - `socks5-proxies.txt` (SOCKS5 only)
- 🚫 Maintains a `blacklist.txt` for invalid proxies, automatically filtering them out in future runs.
- ⚡ Optimized for performance with UVLoop on Linux runners (2-4x faster).
- 🤖 Fully automated via GitHub Actions, running every 6 hours.
- 📝 Outputs proxies in `IP:PORT` format.

### 🛠️ How to Use
Getting started with OtoProxy is simple! Just follow these steps:

1. **Fork the Repository** 🍴
   - Click the **Fork** button at the top of this page to create a copy of the repository under your GitHub account.

2. **Add a GitHub Token** 🔑
   - Generate a **Personal Access Token (PAT)**:
     - Go to **Settings > Developer settings > Personal access tokens > Tokens (classic)** in your GitHub account.
     - Create a new token with the `repo` scope (for read/write access).
   - Add the token to your repository:
     - Navigate to **Settings > Secrets and variables > Actions** in your forked repository.
     - Click **New repository secret**.
     - Name the secret `GH_TOKEN` and paste your PAT as the value.

3. **Enable GitHub Actions** ⚙️
   - Ensure GitHub Actions is enabled in your repository (**Settings > Actions > General**).
   - The workflow (`otoproxy.yml`) will automatically run every 6 hours, scraping, verifying, and saving proxies.

4. **Customize (Optional)** 📚
   - Edit `sites.txt` to add or modify proxy source URLs.
   - Check the generated files (`all-proxies.txt`, `blacklist.txt`, etc.) in your repository.

### 📜 License
This project is licensed under the **MIT License**. See the [LICENSE](LICENSE) file for details. 📄

### ⚠️ Disclaimer
OtoProxy is created for **educational purposes** and **knowledge sharing** only. The author is **not responsible** for any illegal activities conducted using this tool. Use it responsibly and ethically. 🛡️

### 🙏 Acknowledgments
- **Grok AI** by xAI for providing invaluable assistance in code development and optimization. 🤖
- **Omar Obando** for the original [ProxyStorm](https://github.com/Omar-Obando/proxystorm-fastest-proxy-scraper-checker.git), which inspired and contributed to parts of this project. 🌟

### 💡 Contributing
Feel free to open issues or submit pull requests to improve OtoProxy! Let’s make it better together. 😄
