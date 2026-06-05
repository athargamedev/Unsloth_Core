#!/usr/bin/env python3
"""
Exporter script to convert pipeline_visualgraph.md into a standalone, beautiful HTML document.
Complies with Frontend Philosophy: Typography with Character, Committed Color, Purposeful Motion,
Brave Spatial Composition, and Atmospheric Depth.
"""

import os
import re
import sys


def parse_and_compile():
    # Paths
    workspace_dir = "/home/athar/Projects/Unsloth_Core"
    md_path = os.path.join(workspace_dir, "docs/reports/pipeline_visualgraph.md")
    html_path = os.path.join(workspace_dir, "docs/reports/pipeline_visualgraph.html")

    # 1. Early Exit & Validation
    if not os.path.exists(md_path):
        print(f"Error: Source file '{md_path}' does not exist.", file=sys.stderr)
        sys.exit(1)

    try:
        import markdown
    except ImportError:
        print(
            "Error: The 'markdown' library is required. Please install it using pip.",
            file=sys.stderr,
        )
        sys.exit(1)

    # 2. Read MD File
    with open(md_path, encoding="utf-8") as f:
        md_content = f.read()

    # 3. Strip Frontmatter (Robustness)
    # Check for frontmatter blocks starting and ending with '---'
    frontmatter_pattern = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
    cleaned_content = frontmatter_pattern.sub("", md_content)

    # 4. Compile Markdown content to HTML
    # We use fenced_code and tables extensions
    html_body = markdown.markdown(cleaned_content, extensions=["fenced_code", "tables"])

    # 5. Define high-fidelity boilerplate with character
    # Pairing Playfair Display (Serif display) with Plus Jakarta Sans (Modern sans-serif)
    # and JetBrains Mono (high-legibility mono)
    boilerplate = f"""<!DOCTYPE html>
<html lang="en" class="h-full scroll-smooth">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Unsloth_Core SFT Training &amp; Evaluation Pipeline Dataflow</title>

    <!-- Tailwind CSS CDN -->
    <script src="https://cdn.tailwindcss.com"></script>

    <!-- Google Fonts for High-Character Typography -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:ital,wght@0,200..800;1,200..800&amp;family=Playfair+Display:ital,wght@0,400..900;1,400..900&amp;family=JetBrains+Mono:ital,wght@0,100..800;1,100..800&amp;display=swap" rel="stylesheet">

    <!-- Style Overrides and Atmosphere -->
    <style>
        /* Modern Font Overrides using imported Google Fonts */
        :root {{
            --font-sans: 'Plus Jakarta Sans', system-ui, -apple-system, sans-serif !important;
            --font-display: 'Playfair Display', Georgia, serif !important;
            --font-mono: 'JetBrains Mono', 'Fira Code', ui-monospace, monospace !important;
        }}

        /* Layout, Overflow & Responsiveness Guards */
        svg {{
            max-width: 100% !important;
            height: auto !important;
            display: block;
            margin-left: auto;
            margin-right: auto;
        }}

        pre, code {{
            max-width: 100%;
            overflow-x: auto;
        }}

        /* Atmospheric Texture and depth (Pillar 5 of Frontend Philosophy) */
        body {{
            position: relative;
            background-color: var(--background, oklch(0.15 0.02 260)); /* Fallback if CSS variables from content aren't loaded yet */
            color: var(--foreground, oklch(0.90 0.01 260));
        }}

        /* Add subtle modern gradient mesh background */
        body::before {{
            content: "";
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            z-index: -10;
            background:
                radial-gradient(circle at 10% 10%, rgba(147, 51, 234, 0.03) 0%, transparent 40%),
                radial-gradient(circle at 90% 80%, rgba(59, 130, 246, 0.03) 0%, transparent 40%),
                radial-gradient(circle at 50% 50%, rgba(16, 185, 129, 0.02) 0%, transparent 50%);
        }}

        /* Subtle noise overlay for organic texture */
        body::after {{
            content: "";
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            opacity: 0.012;
            pointer-events: none;
            z-index: 10000;
            background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.75' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E");
        }}

        /* Custom scrollbar matching the dark theme aesthetic */
        ::-webkit-scrollbar {{
            width: 10px;
            height: 10px;
        }}
        ::-webkit-scrollbar-track {{
            background: var(--background, oklch(0.15 0.02 260));
        }}
        ::-webkit-scrollbar-thumb {{
            background: var(--border, oklch(0.35 0.02 260));
            border-radius: 5px;
        }}
        ::-webkit-scrollbar-thumb:hover {{
            background: var(--primary, oklch(0.75 0.18 280));
        }}

        /* Animation class for smooth reveals (Pillar 3 of Frontend Philosophy) */
        @keyframes fadeInSlideUp {{
            from {{
                opacity: 0;
                transform: translateY(20px);
            }}
            to {{
                opacity: 1;
                transform: translateY(0);
            }}
        }}

        .animate-fade-in-up {{
            animation: fadeInSlideUp 0.8s cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }}

        /* Soft, dramatic hover effect for interactive cards */
        .card-hover-effect {{
            transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
        }}
        .card-hover-effect:hover {{
            transform: translateY(-4px);
            box-shadow: 0 12px 30px -10px rgba(147, 51, 234, 0.2);
            border-color: var(--primary) !important;
        }}
    </style>
</head>
<body class="font-sans antialiased selection:bg-purple-600/30 selection:text-purple-200">
    <div class="animate-fade-in-up">
        {html_body}
    </div>
</body>
</html>
"""

    # 6. Write final standalone HTML
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(boilerplate)

    print(f"Success! Standalone visualgraph HTML written to: {html_path}")


if __name__ == "__main__":
    parse_and_compile()
