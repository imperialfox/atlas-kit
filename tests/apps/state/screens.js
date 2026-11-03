// The register of a made-up app's screens: one permanent ID each. Read by the app (to mark each screen with
// data-screen) and by the Atlas kit (from the running page).
window.SCREENS = [
  {id: 'TL-001', name: 'Home', key: 'home', area: 'Home', kind: 'Tab', parts: ['summary', 'add-button']},
  {id: 'TL-002', name: 'List', key: 'list', area: 'List', kind: 'Tab', parts: ['item-row']},
  {id: 'TL-003', name: 'Settings', key: window.APP_VERSION === 2 ? 'prefs' : 'settings', aliases: window.APP_VERSION === 2 ? ['settings'] : [],
   area: 'Settings', kind: 'Tab', parts: ['about-row', 'clear-button']},
  {id: 'TL-004', name: 'About', key: 'about', area: 'Settings', kind: 'Sub-page', parts: ['back-button']},
  {id: 'TL-005', name: 'Add an item', key: 'add', area: 'Home', kind: 'Sheet', parts: ['title-field', 'save-button']},
  {id: 'TL-006', name: 'Item menu', key: 'menu', area: 'List', kind: 'Sheet', parts: ['done-button']},
].concat(window.APP_VERSION === 2 ? [{id: 'TL-007', name: 'Archive', key: 'archive', area: 'List', kind: 'Screen'}] : []);
