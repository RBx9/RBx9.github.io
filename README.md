# RBx9 Repo

A reusable Sileo / APT repository for jailbreak tweaks developed by **RBx9**.

**Sileo source URL (after GitHub Pages is enabled):**
https://rbx9.github.io/

## Install in Sileo
1. Open Sileo → Sources → +.
2. Paste `https://rbx9.github.io/`.
3. Refresh sources, choose **RBx9 Repo**, and install a compatible package.

The first included tweak is **DuoBar v0.2.0** for Dopamine RootHide / iOS 16.
Only install packages compatible with your jailbreak; RootHide packages are not standard rootless packages.

## Add more tweaks later
Each new tweak can live in its **own GitHub repository**. Publish its .deb as a GitHub Release asset, then add a line to [package-sources.txt](package-sources.txt) in this repository:

```text
https://github.com/OWNER/TWEAK/releases/download/TAG/installer.deb|installer.deb|SHA256
```

Committing `package-sources.txt` automatically downloads the release assets, verifies SHA-256 hashes, and regenerates the Sileo/APT metadata. Run **Build Sileo Repository** from Actions to refresh it manually. Keep existing manifest lines to retain older packages.

## Hosting (one-time)
In this repository's [Settings → Pages](https://github.com/RBx9/RBx9.github.io/settings/pages), select **Deploy from a branch**, choose **main** and **/(root)**, then Save. Your source is `https://rbx9.github.io/`.

Generated index files: `Packages`, `Packages.gz`, `Packages.bz2`, `Release`. Binaries: `debs/`. Source details: `index.html`.

This is a personal repository, **not affiliated with Sileo or RootHide**.
