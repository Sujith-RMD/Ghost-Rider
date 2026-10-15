import {defineConfig} from '@playwright/test';
export default defineConfig({
 testDir:'./e2e',testMatch:'refinement.spec.ts',outputDir:`test-results/refinement-${Date.now()}`,
 workers:1,timeout:45000,reporter:[['list']],
 use:{baseURL:'http://127.0.0.1:5187',viewport:{width:1920,height:1080},launchOptions:{executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE}},
 webServer:{command:'npm run preview -- --outDir dist-demo --port 5187 --strictPort',url:'http://127.0.0.1:5187',reuseExistingServer:false,timeout:60000},
});
