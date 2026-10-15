# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: refinement.spec.ts >> reference refinement captures at the confirmed 1920 x 1080 desktop size
- Location: e2e\refinement.spec.ts:5:1

# Error details

```
Error: [
  {
    "id": "color-contrast",
    "impact": "serious",
    "tags": [
      "cat.color",
      "wcag2aa",
      "wcag143",
      "TTv5",
      "TT13.c",
      "EN-301-549",
      "EN-9.1.4.3",
      "ACT",
      "RGAAv4",
      "RGAA-3.2.1"
    ],
    "description": "Ensure the contrast between foreground and background colors meets WCAG 2 AA minimum contrast ratio thresholds",
    "help": "Elements must meet minimum color contrast ratio thresholds",
    "helpUrl": "https://dequeuniversity.com/rules/axe/4.14/color-contrast?application=playwright",
    "nodes": [
      {
        "any": [
          {
            "id": "color-contrast",
            "data": {
              "fgColor": "#7f837a",
              "bgColor": "#122221",
              "contrastRatio": 4.25,
              "fontSize": "9.0pt (12px)",
              "fontWeight": "normal",
              "messageKey": null,
              "expectedContrastRatio": "4.5:1"
            },
            "relatedNodes": [
              {
                "html": "<button class=\"quality-tile accepted\" aria-pressed=\"false\">",
                "target": [
                  ".quality-tile.accepted"
                ]
              }
            ],
            "impact": "serious",
            "message": "Element has insufficient color contrast of 4.25 (foreground color: #7f837a, background color: #122221, font size: 9.0pt (12px), font weight: normal). Expected contrast ratio of 4.5:1"
          }
        ],
        "all": [],
        "none": [],
        "impact": "serious",
        "html": "<span class=\"quality-name\">Accepted</span>",
        "target": [
          ".quality-tile.accepted > .quality-name"
        ],
        "failureSummary": "Fix any of the following:\n  Element has insufficient color contrast of 4.25 (foreground color: #7f837a, background color: #122221, font size: 9.0pt (12px), font weight: normal). Expected contrast ratio of 4.5:1"
      },
      {
        "any": [
          {
            "id": "color-contrast",
            "data": {
              "fgColor": "#7f837a",
              "bgColor": "#122221",
              "contrastRatio": 4.25,
              "fontSize": "9.0pt (12px)",
              "fontWeight": "normal",
              "messageKey": null,
              "expectedContrastRatio": "4.5:1"
            },
            "relatedNodes": [
              {
                "html": "<button class=\"quality-tile limited\" aria-pressed=\"false\">",
                "target": [
                  ".limited.quality-tile"
                ]
              }
            ],
            "impact": "serious",
            "message": "Element has insufficient color contrast of 4.25 (foreground color: #7f837a, background color: #122221, font size: 9.0pt (12px), font weight: normal). Expected contrast ratio of 4.5:1"
          }
        ],
        "all": [],
        "none": [],
        "impact": "serious",
        "html": "<span class=\"quality-name\">Limited</span>",
        "target": [
          ".limited.quality-tile > .quality-name"
        ],
        "failureSummary": "Fix any of the following:\n  Element has insufficient color contrast of 4.25 (foreground color: #7f837a, background color: #122221, font size: 9.0pt (12px), font weight: normal). Expected contrast ratio of 4.5:1"
      },
      {
        "any": [
          {
            "id": "color-contrast",
            "data": {
              "fgColor": "#7f837a",
              "bgColor": "#122221",
              "contrastRatio": 4.25,
              "fontSize": "9.0pt (12px)",
              "fontWeight": "normal",
              "messageKey": null,
              "expectedContrastRatio": "4.5:1"
            },
            "relatedNodes": [
              {
                "html": "<button class=\"quality-tile rejected\" aria-pressed=\"false\">",
                "target": [
                  ".rejected.quality-tile"
                ]
              }
            ],
            "impact": "serious",
            "message": "Element has insufficient color contrast of 4.25 (foreground color: #7f837a, background color: #122221, font size: 9.0pt (12px), font weight: normal). Expected contrast ratio of 4.5:1"
          }
        ],
        "all": [],
        "none": [],
        "impact": "serious",
        "html": "<span class=\"quality-name\">Rejected</span>",
        "target": [
          ".rejected.quality-tile > .quality-name"
        ],
        "failureSummary": "Fix any of the following:\n  Element has insufficient color contrast of 4.25 (foreground color: #7f837a, background color: #122221, font size: 9.0pt (12px), font weight: normal). Expected contrast ratio of 4.5:1"
      }
    ]
  }
]

expect(received).toEqual(expected) // deep equality

- Expected  -   1
+ Received  + 128

- Array []
+ Array [
+   Object {
+     "description": "Ensure the contrast between foreground and background colors meets WCAG 2 AA minimum contrast ratio thresholds",
+     "help": "Elements must meet minimum color contrast ratio thresholds",
+     "helpUrl": "https://dequeuniversity.com/rules/axe/4.14/color-contrast?application=playwright",
+     "id": "color-contrast",
+     "impact": "serious",
+     "nodes": Array [
+       Object {
+         "all": Array [],
+         "any": Array [
+           Object {
+             "data": Object {
+               "bgColor": "#122221",
+               "contrastRatio": 4.25,
+               "expectedContrastRatio": "4.5:1",
+               "fgColor": "#7f837a",
+               "fontSize": "9.0pt (12px)",
+               "fontWeight": "normal",
+               "messageKey": null,
+             },
+             "id": "color-contrast",
+             "impact": "serious",
+             "message": "Element has insufficient color contrast of 4.25 (foreground color: #7f837a, background color: #122221, font size: 9.0pt (12px), font weight: normal). Expected contrast ratio of 4.5:1",
+             "relatedNodes": Array [
+               Object {
+                 "html": "<button class=\"quality-tile accepted\" aria-pressed=\"false\">",
+                 "target": Array [
+                   ".quality-tile.accepted",
+                 ],
+               },
+             ],
+           },
+         ],
+         "failureSummary": "Fix any of the following:
+   Element has insufficient color contrast of 4.25 (foreground color: #7f837a, background color: #122221, font size: 9.0pt (12px), font weight: normal). Expected contrast ratio of 4.5:1",
+         "html": "<span class=\"quality-name\">Accepted</span>",
+         "impact": "serious",
+         "none": Array [],
+         "target": Array [
+           ".quality-tile.accepted > .quality-name",
+         ],
+       },
+       Object {
+         "all": Array [],
+         "any": Array [
+           Object {
+             "data": Object {
+               "bgColor": "#122221",
+               "contrastRatio": 4.25,
+               "expectedContrastRatio": "4.5:1",
+               "fgColor": "#7f837a",
+               "fontSize": "9.0pt (12px)",
+               "fontWeight": "normal",
+               "messageKey": null,
+             },
+             "id": "color-contrast",
+             "impact": "serious",
+             "message": "Element has insufficient color contrast of 4.25 (foreground color: #7f837a, background color: #122221, font size: 9.0pt (12px), font weight: normal). Expected contrast ratio of 4.5:1",
+             "relatedNodes": Array [
+               Object {
+                 "html": "<button class=\"quality-tile limited\" aria-pressed=\"false\">",
+                 "target": Array [
+                   ".limited.quality-tile",
+                 ],
+               },
+             ],
+           },
+         ],
+         "failureSummary": "Fix any of the following:
+   Element has insufficient color contrast of 4.25 (foreground color: #7f837a, background color: #122221, font size: 9.0pt (12px), font weight: normal). Expected contrast ratio of 4.5:1",
+         "html": "<span class=\"quality-name\">Limited</span>",
+         "impact": "serious",
+         "none": Array [],
+         "target": Array [
+           ".limited.quality-tile > .quality-name",
+         ],
+       },
+       Object {
+         "all": Array [],
+         "any": Array [
+           Object {
+             "data": Object {
+               "bgColor": "#122221",
+               "contrastRatio": 4.25,
+               "expectedContrastRatio": "4.5:1",
+               "fgColor": "#7f837a",
+               "fontSize": "9.0pt (12px)",
+               "fontWeight": "normal",
+               "messageKey": null,
+             },
+             "id": "color-contrast",
+             "impact": "serious",
+             "message": "Element has insufficient color contrast of 4.25 (foreground color: #7f837a, background color: #122221, font size: 9.0pt (12px), font weight: normal). Expected contrast ratio of 4.5:1",
+             "relatedNodes": Array [
+               Object {
+                 "html": "<button class=\"quality-tile rejected\" aria-pressed=\"false\">",
+                 "target": Array [
+                   ".rejected.quality-tile",
+                 ],
+               },
+             ],
+           },
+         ],
+         "failureSummary": "Fix any of the following:
+   Element has insufficient color contrast of 4.25 (foreground color: #7f837a, background color: #122221, font size: 9.0pt (12px), font weight: normal). Expected contrast ratio of 4.5:1",
+         "html": "<span class=\"quality-name\">Rejected</span>",
+         "impact": "serious",
+         "none": Array [],
+         "target": Array [
+           ".rejected.quality-tile > .quality-name",
+         ],
+       },
+     ],
+     "tags": Array [
+       "cat.color",
+       "wcag2aa",
+       "wcag143",
+       "TTv5",
+       "TT13.c",
+       "EN-301-549",
+       "EN-9.1.4.3",
+       "ACT",
+       "RGAAv4",
+       "RGAA-3.2.1",
+     ],
+   },
+ ]
```

# Page snapshot

```yaml
- generic [ref=f1e3]:
  - link "Skip to content" [ref=f1e4] [cursor=pointer]:
    - /url: "#main"
  - generic [ref=f1e5]:
    - text: Mock data. Values are not measurements.
    - generic [ref=f1e7]: Interface preview
  - banner [ref=f1e8]:
    - link "RoadSight home" [ref=f1e9] [cursor=pointer]:
      - /url: /
      - generic [ref=f1e14]: RoadSight AI
    - navigation "Main navigation" [ref=f1e15]:
      - link "Route map" [ref=f1e16] [cursor=pointer]:
        - /url: /
      - link "Assess" [ref=f1e17] [cursor=pointer]:
        - /url: /assess
      - link "Live" [ref=f1e18] [cursor=pointer]:
        - /url: /live
      - link "Samples" [ref=f1e19] [cursor=pointer]:
        - /url: /samples
      - link "Reports" [ref=f1e20] [cursor=pointer]:
        - /url: /reports
      - link "System" [ref=f1e21] [cursor=pointer]:
        - /url: /system
    - link "API not connected" [ref=f1e22] [cursor=pointer]:
      - /url: /system
  - main [ref=f1e24]:
    - generic [ref=f1e25]:
      - complementary "Route evidence" [ref=f1e26]:
        - generic [ref=f1e27]:
          - button "All 5" [pressed] [ref=f1e28] [cursor=pointer]:
            - generic [ref=f1e29]: All
            - generic [ref=f1e30]: "5"
          - button "Live 1" [ref=f1e32] [cursor=pointer]:
            - generic [ref=f1e33]: Live
            - generic [ref=f1e34]: "1"
          - button "Replay 2" [ref=f1e36] [cursor=pointer]:
            - generic [ref=f1e37]: Replay
            - generic [ref=f1e38]: "2"
          - button "Still 2" [ref=f1e40] [cursor=pointer]:
            - generic [ref=f1e41]: Still
            - generic [ref=f1e42]: "2"
        - generic [ref=f1e44]:
          - heading "Image quality" [level=2] [ref=f1e46]
          - generic [ref=f1e47]:
            - button "Accepted 3" [ref=f1e48] [cursor=pointer]:
              - generic [ref=f1e52]: Accepted
              - generic [ref=f1e53]: "3"
            - button "Limited 1" [ref=f1e55] [cursor=pointer]:
              - generic [ref=f1e60]: Limited
              - generic [ref=f1e61]: "1"
            - button "Rejected 1" [ref=f1e63] [cursor=pointer]:
              - generic [ref=f1e68]: Rejected
              - generic [ref=f1e69]: "1"
        - generic [ref=f1e71]:
          - generic [ref=f1e72]:
            - heading "Condition along route" [level=2] [ref=f1e73]
            - link "Open Condition along route" [ref=f1e74] [cursor=pointer]:
              - /url: /sessions/session-demo
          - generic [ref=f1e78]:
            - generic [ref=f1e79]:
              - generic [ref=f1e80]:
                - generic [ref=f1e82]:
                  - text: "68"
                  - generic [ref=f1e83]: ".1"
                - generic "This reference comparison is not yet calibrated to human ratings." [ref=f1e84]: Provisional reference-deviation index
              - button "View data" [ref=f1e85] [cursor=pointer]
            - group "Condition along route distance. The line breaks where no accepted samples exist." [ref=f1e86]:
              - generic [ref=f1e87]: "40"
              - generic [ref=f1e89]: "60"
              - generic [ref=f1e91]: "80"
              - generic "Not sampled. We have no measurements for this stretch." [ref=f1e94]
              - generic "Not sampled. We have no measurements for this stretch." [ref=f1e96]
              - button "Select bin-1" [ref=f1e100]
              - button "Select bin-2" [ref=f1e102]
              - button "Select bin-3" [ref=f1e104]
              - button "Select bin-6" [ref=f1e106]
              - button "Select bin-7" [ref=f1e108]
              - button "Select bin-8" [ref=f1e110]
              - button "Select bin-9" [ref=f1e112]
              - button "Select bin-10" [ref=f1e114]
              - button "Select bin-11" [ref=f1e116]
              - button "Select bin-12" [ref=f1e119]
              - generic [ref=f1e121]: 0 m
              - generic [ref=f1e122]: 600 m
            - generic [ref=f1e123]:
              - generic [ref=f1e124]: Sampled strip
              - generic [ref=f1e126]: Not sampled
          - generic [ref=f1e128]:
            - generic [ref=f1e129]: Coverage
            - generic [ref=f1e131]:
              - text: "83"
              - generic [ref=f1e132]: ".3"
              - generic [ref=f1e133]: "%"
        - generic [ref=f1e134]:
          - heading "Recent samples" [level=2] [ref=f1e135]
          - generic [ref=f1e136]: 5 shown
        - generic [ref=f1e137]:
          - link "Open sample-01, still, accepted" [ref=f1e138] [cursor=pointer]:
            - /url: /samples/sample-01
            - img "Placeholder road-texture illustration, not captured evidence" [ref=f1e140]
            - generic [ref=f1e142]:
              - generic [ref=f1e143]: Still
              - generic [ref=f1e148]: Accepted
            - generic [ref=f1e154]:
              - heading "15:44:32" [level=3] [ref=f1e156]
              - paragraph [ref=f1e157]: Placeholder texture
              - generic [ref=f1e158]:
                - generic [ref=f1e159]: No GPS
                - generic [ref=f1e160]: Calibrated fixture
              - generic [ref=f1e161]:
                - generic [ref=f1e162]: Review
                - generic [ref=f1e166]: Inspect
          - link "Open sample-02, replay, limited" [ref=f1e169] [cursor=pointer]:
            - /url: /samples/sample-02
            - img "Placeholder road-texture illustration, not captured evidence" [ref=f1e171]
            - generic [ref=f1e173]:
              - generic [ref=f1e174]: Replay
              - generic [ref=f1e178]: Limited
            - generic [ref=f1e185]:
              - heading "15:44:26" [level=3] [ref=f1e187]
              - paragraph [ref=f1e188]: Placeholder texture
              - generic [ref=f1e189]:
                - generic [ref=f1e190]: No GPS
                - generic [ref=f1e191]: Uncalibrated
              - generic [ref=f1e192]: Unknown
          - link "Open sample-03, live, accepted" [ref=f1e197] [cursor=pointer]:
            - /url: /samples/sample-03
            - img "Placeholder road-texture illustration, not captured evidence" [ref=f1e199]
            - generic [ref=f1e201]:
              - generic [ref=f1e202]: Live
              - generic [ref=f1e209]: Accepted
            - generic [ref=f1e215]:
              - heading "15:44:20" [level=3] [ref=f1e217]
              - paragraph [ref=f1e218]: Placeholder texture
              - generic [ref=f1e219]:
                - generic [ref=f1e220]: No GPS
                - generic [ref=f1e221]: Calibrated fixture
              - generic [ref=f1e222]: Good
          - link "Open sample-04, still, rejected" [ref=f1e226] [cursor=pointer]:
            - /url: /samples/sample-04
            - img "Placeholder road-texture illustration, not captured evidence" [ref=f1e228]
            - generic [ref=f1e230]:
              - generic [ref=f1e231]: Still
              - generic [ref=f1e236]: Rejected
            - generic [ref=f1e243]:
              - heading "15:44:14" [level=3] [ref=f1e245]
              - paragraph [ref=f1e246]: Placeholder texture
              - generic [ref=f1e247]:
                - generic [ref=f1e248]: No GPS
                - generic [ref=f1e249]: Calibrated fixture
              - generic [ref=f1e250]: Unknown
          - link "Open sample-05, replay, accepted" [ref=f1e255] [cursor=pointer]:
            - /url: /samples/sample-05
            - img "Placeholder road-texture illustration, not captured evidence" [ref=f1e257]
            - generic [ref=f1e259]:
              - generic [ref=f1e260]: Replay
              - generic [ref=f1e264]: Accepted
            - generic [ref=f1e270]:
              - heading "15:44:08" [level=3] [ref=f1e272]
              - paragraph [ref=f1e273]: Placeholder texture
              - generic [ref=f1e274]:
                - generic [ref=f1e275]: No GPS
                - generic [ref=f1e276]: Calibrated fixture
              - generic [ref=f1e277]:
                - generic [ref=f1e278]: Bad
                - generic [ref=f1e282]: Inspect
      - region "Route condition" [ref=f1e285]:
        - generic:
          - heading "Route condition" [level=1]
          - paragraph: Observed evidence. Visible limits.
          - generic [ref=f1e286]:
            - group [ref=f1e287]:
              - generic "Inspection preview" [ref=f1e288] [cursor=pointer]
            - button "Layers" [ref=f1e293] [cursor=pointer]
            - generic [ref=f1e300]: Replay
        - generic [ref=f1e304]: Abstract backdrop, not a map
        - generic [ref=f1e318]:
          - heading "Map unavailable" [level=2] [ref=f1e319]
          - paragraph [ref=f1e320]: This session has no GPS fix, so condition is shown by distance only.
        - generic [ref=f1e322]:
          - generic [ref=f1e323]:
            - heading "Route coverage" [level=2] [ref=f1e324]
            - link "Open Route coverage" [ref=f1e325] [cursor=pointer]:
              - /url: /sessions/session-demo
          - generic [ref=f1e330]:
            - text: "83"
            - generic [ref=f1e331]: ".3"
            - generic [ref=f1e332]: "%"
          - paragraph [ref=f1e333]:
            - generic [ref=f1e335]:
              - text: "500"
              - generic [ref=f1e336]: m
            - text: of
            - generic [ref=f1e338]:
              - text: "600"
              - generic [ref=f1e339]: m
            - generic [ref=f1e340]: Length coverage, not full-lane area
          - generic [ref=f1e341]: Observed strip only
        - generic [ref=f1e344]:
          - generic [ref=f1e345]:
            - generic [ref=f1e346]:
              - generic [ref=f1e347]: Linear distance report
              - generic [ref=f1e348]: 50 m reporting bins
            - generic [ref=f1e349]:
              - 'button "bin-1: good" [ref=f1e350] [cursor=pointer]':
                - generic [ref=f1e351]: "1"
              - 'button "bin-2: good" [ref=f1e352] [cursor=pointer]':
                - generic [ref=f1e353]: "2"
              - 'button "bin-3: good" [ref=f1e354] [cursor=pointer]':
                - generic [ref=f1e355]: "3"
              - 'button "bin-4: not sampled" [ref=f1e356] [cursor=pointer]':
                - generic [ref=f1e357]: "4"
              - 'button "bin-5: not sampled" [ref=f1e358] [cursor=pointer]':
                - generic [ref=f1e359]: "5"
              - 'button "bin-6: review" [ref=f1e360] [cursor=pointer]':
                - generic [ref=f1e361]: "6"
              - 'button "bin-7: review" [ref=f1e362] [cursor=pointer]':
                - generic [ref=f1e363]: "7"
              - 'button "bin-8: review" [ref=f1e364] [cursor=pointer]':
                - generic [ref=f1e365]: "8"
              - 'button "bin-9: review" [ref=f1e366] [cursor=pointer]':
                - generic [ref=f1e367]: "9"
              - 'button "bin-10: review" [ref=f1e368] [cursor=pointer]':
                - generic [ref=f1e369]: "10"
              - 'button "bin-11: bad" [ref=f1e370] [cursor=pointer]':
                - generic [ref=f1e371]: "11"
              - 'button "bin-12: review" [ref=f1e372] [cursor=pointer]':
                - generic [ref=f1e373]: "12"
            - generic [ref=f1e374]:
              - generic [ref=f1e375]: 0 m
              - generic [ref=f1e377]:
                - text: "600"
                - generic [ref=f1e378]: m
            - generic [ref=f1e379]:
              - generic [ref=f1e380]: Good
              - generic [ref=f1e383]: Bad
              - generic [ref=f1e387]: Review
              - generic [ref=f1e391]: Not sampled
          - paragraph [ref=f1e392]: Illustrative session. Unsampled stretches carry no condition assessment.
        - button "Segment evidence12 reporting bins" [ref=f1e394] [cursor=pointer]:
          - generic [ref=f1e395]:
            - text: Segment evidence
            - generic [ref=f1e396]: 12 reporting bins
```

# Test source

```ts
  1  | import { test, expect } from "@playwright/test";
  2  | import AxeBuilder from "@axe-core/playwright";
  3  | import { mkdir } from "node:fs/promises";
  4  | import path from "node:path";
  5  | test("reference refinement captures at the confirmed 1920 x 1080 desktop size", async ({
  6  |   page,
  7  | }) => {
  8  |   const folder = path.resolve("../docs/frontend/screenshots/refinement");
  9  |   await mkdir(folder, { recursive: true });
  10 |   const cases = [
  11 |     ["route-simulated", "/?fixture=simulated"],
  12 |     ["route-no-gps", "/?fixture=no-gps"],
  13 |     ["assess-idle", "/assess"],
  14 |     ["assess-selected", "/assess"],
  15 |     ["sample", "/samples/sample-01"],
  16 |     ["live", "/live"],
  17 |   ] as const;
  18 |   for (const [name, url] of cases) {
  19 |     await page.goto(url);
  20 |     await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
  21 |     await page.evaluate(() => document.fonts.ready);
  22 |     if (name === "assess-selected")
  23 |       await page
  24 |         .getByLabel("Choose road image")
  25 |         .setInputFiles(path.resolve("public/fixtures/road-placeholder.png"));
  26 |     if (name === "route-simulated") {
  27 |       await expect(
  28 |         page.getByText("Simulated route", { exact: true }),
  29 |       ).toBeVisible();
  30 |       await expect(
  31 |         page.getByText("Abstract backdrop, not a map", { exact: true }),
  32 |       ).toBeVisible();
  33 |     }
  34 |     if (name === "route-no-gps") {
  35 |       await expect(
  36 |         page.getByText(
  37 |           "This session has no GPS fix, so condition is shown by distance only.",
  38 |         ),
  39 |       ).toBeVisible();
  40 |       await expect(
  41 |         page.getByText("Simulated route", { exact: true }),
  42 |       ).toHaveCount(0);
  43 |     }
  44 |     if (name.startsWith("assess")) {
  45 |       await expect(
  46 |         page.getByRole("heading", { name: "Preview processing states" }),
  47 |       ).toHaveCount(0);
  48 |       await expect(page.locator("select")).toHaveCount(0);
  49 |       await expect(page.locator(".dev-fixture-panel")).toHaveCount(0);
  50 |     }
  51 |     expect(
  52 |       await page.evaluate(
  53 |         () => document.documentElement.scrollWidth <= innerWidth,
  54 |       ),
  55 |     ).toBe(true);
  56 |     const result = await new AxeBuilder({ page })
  57 |       .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
  58 |       .analyze();
  59 |     expect(
  60 |       result.violations,
  61 |       JSON.stringify(result.violations, null, 2),
> 62 |     ).toEqual([]);
     |       ^ Error: [
  63 |     await page.screenshot({
  64 |       path: path.join(folder, `${name}-1920x1080.png`),
  65 |       fullPage: false,
  66 |       animations: "disabled",
  67 |     });
  68 |   }
  69 | });
  70 | 
```