import { portfolioPage } from './portfolio.js';

// OVERVIEW > Team (project directors): the PMs the director leads, their PM level, current workload and the projects they manage.
export default function team(root) {
  return portfolioPage(root, { page: 'team', mode: 'direct', tab: 'team', directorOnly: true, title: 'Team',
    sub: 'The project managers on the projects you direct, or who report to you: PM level, how loaded each is, and which projects they manage.' });
}
