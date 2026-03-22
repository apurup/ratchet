import React from 'react';
import ComponentCreator from '@docusaurus/ComponentCreator';

export default [
  {
    path: '/ratchet/docs',
    component: ComponentCreator('/ratchet/docs', 'efa'),
    routes: [
      {
        path: '/ratchet/docs',
        component: ComponentCreator('/ratchet/docs', '4dc'),
        routes: [
          {
            path: '/ratchet/docs',
            component: ComponentCreator('/ratchet/docs', '2a6'),
            routes: [
              {
                path: '/ratchet/docs/api-reference',
                component: ComponentCreator('/ratchet/docs/api-reference', '1b3'),
                exact: true,
                sidebar: "tutorialSidebar"
              },
              {
                path: '/ratchet/docs/architecture',
                component: ComponentCreator('/ratchet/docs/architecture', 'db4'),
                exact: true,
                sidebar: "tutorialSidebar"
              },
              {
                path: '/ratchet/docs/getting-started',
                component: ComponentCreator('/ratchet/docs/getting-started', '24c'),
                exact: true,
                sidebar: "tutorialSidebar"
              },
              {
                path: '/ratchet/docs/intro',
                component: ComponentCreator('/ratchet/docs/intro', '8bd'),
                exact: true,
                sidebar: "tutorialSidebar"
              },
              {
                path: '/ratchet/docs/skills',
                component: ComponentCreator('/ratchet/docs/skills', 'd81'),
                exact: true,
                sidebar: "tutorialSidebar"
              }
            ]
          }
        ]
      }
    ]
  },
  {
    path: '/ratchet/',
    component: ComponentCreator('/ratchet/', '8a2'),
    exact: true
  },
  {
    path: '*',
    component: ComponentCreator('*'),
  },
];
