import Vue from 'vue'
import VueRouter from 'vue-router'
import Home from '@/components/Home'
import Dashboard from '@/components/Dashboard'
import Tickets from '@/components/Tickets'
import TicketsEdit from '@/components/TicketsEdit'
import RelVals from '@/components/RelVals'
import RelValsEdit from '@/components/RelValsEdit'
import RelValsMultipleEdit from '@/components/RelValsMultipleEdit'
import qs from 'qs';


Vue.use(VueRouter)

const routes = [
  {
    path: '/',
    name: 'home',
    component: Home
  },
  {
    path: '/dashboard',
    name: 'dashboard',
    component: Dashboard
  },
  {
    path: '/tickets/edit',
    name: 'tickets_edit',
    component: TicketsEdit
  },
  {
    path: '/tickets',
    name: 'tickets',
    component: Tickets
  },
  {
    path: '/relvals/edit',
    name: 'relvals_edit',
    component: RelValsEdit
  },
  {
    path: '/relvals/edit_many',
    name: 'relvals_edit_many',
    component: RelValsMultipleEdit
  },
  {
    path: '/relvals',
    name: 'relvals',
    component: RelVals
  },
]

const router = new VueRouter({
  mode: 'history',
  base: process.env.BASE_URL,
  stringifyQuery: query => {
    var result = qs.stringify(query);
    // Do not encode asterisks
    result = result.replace(/%2A/g, '*').replace(/%2F/g, '/').replace(/%21/g, '!').replace(/%2C/g, ',');
    return result ? ('?' + result) : '';
  },
  routes
})

export default router
