import {enhanceCommands} from './command-copy.mjs?v=20261016-public1';
import {enhanceFigures} from './figure-viewer.mjs?v=20261016-public1';

const main=document.querySelector('main');
if(main){enhanceCommands(main);enhanceFigures(main);}
