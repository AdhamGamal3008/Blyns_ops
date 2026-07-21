import type { StorybookConfig } from "@storybook/react-vite";

const config: StorybookConfig = {
  stories: ["../src/**/*.stories.@(ts|tsx)"],
  addons: [],
  framework: {
    name: "@storybook/react-vite",
    options: {},
  },
  viteFinal: async (viteConfig) => {
    // Pre-bundle the heavier libs up front. Without this, Vite discovers them
    // mid-session and re-optimizes, which can leave two React copies loaded at
    // once ("Invalid hook call" from useReactTable / recharts).
    viteConfig.optimizeDeps = {
      ...viteConfig.optimizeDeps,
      include: [
        ...(viteConfig.optimizeDeps?.include ?? []),
        "@tanstack/react-table",
        "recharts",
        "framer-motion",
        "react-router-dom",
      ],
    };
    viteConfig.resolve = {
      ...viteConfig.resolve,
      dedupe: [...(viteConfig.resolve?.dedupe ?? []), "react", "react-dom"],
    };
    return viteConfig;
  },
};

export default config;
