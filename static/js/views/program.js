import { portfolioPage } from './portfolio.js';

// OVERVIEW > Program (project directors): the projects the director directs, with the overview, project chart, combined CBS and clients.
export default function program(root) {
  return portfolioPage(root, { page: 'program', mode: 'direct', directorOnly: true, title: 'Program',
    sub: 'The projects you direct as project director, side by side (a child project takes its parent\'s director). Click a project to open it.' });
}
