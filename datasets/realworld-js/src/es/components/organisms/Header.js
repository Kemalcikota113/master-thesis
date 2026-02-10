// @ts-check

/* global CustomEvent */
/* global HTMLElement */

import { secureImageSrc } from '../../helpers/Utils.js'

/**
 * https://github.com/Weedshaker/event-driven-web-components-realworld-example-app/blob/master/FRONTEND_INSTRUCTIONS.md#header
 * As an organism, this component shall hold molecules and/or atoms
 *
 * @export
 * @class Header
 */
export default class Header extends HTMLElement {
  constructor () {
    super()

    /**
     * Listens to the event name/typeArg: 'user'
     *
     * @param {CustomEvent & {detail: import("../controllers/User.js").UserEventDetail}} event
     */
    this.userListener = event => {
      event.detail.fetch.then(user => {
        if (this.shouldComponentRender(user)) this.render(user)
        this.user = user
      }).catch(error => {
        console.log(`Error@UserFetch: ${error}`)
        if (this.shouldComponentRender(null)) this.render(null)
        this.user = null
      })
    }
  }

  connectedCallback () {
    this.user = undefined

    this.render()
    document.body.addEventListener('user', this.userListener)
    this.dispatchEvent(new CustomEvent('getUser', {
      bubbles: true,
      cancelable: true,
      composed: true
    }))
  }

  disconnectedCallback () {
    document.body.removeEventListener('user', this.userListener)
  }

  /**
   * evaluates if a render is necessary
   *
   * @param {import("../../helpers/Interfaces.js").User} user
   * @return {boolean}
   */
  shouldComponentRender (user) {
    return this.user !== user
  }

  /**
   * renders the header within the body, which is in this case the navbar
   *
   * @param {import("../../helpers/Interfaces.js").User} [user = undefined]
   * @return {void}
   */
  render (user) {
    this.innerHTML = /* html */ `
      <nav class="navbar navbar-light">
        <div class="container">
          <a class="navbar-brand" href="#/">conduit</a>
          <ul class="nav navbar-nav pull-xs-right">
            <li class="nav-item">
              <!-- Add "active" class when you're on that page" -->
              <a class="nav-link active" href="#/">Home</a>
            </li>
            ${user ? /* html */ `
              <li class="nav-item">
                <a class="nav-link" href="#/editor">
                  <i class="ion-compose"></i>&nbsp;New Post
                </a>
              </li>
              <li class="nav-item">
                <a class="nav-link" href="#/settings">
                  <i class="ion-gear-a"></i>&nbsp;Settings
                </a>
              </li>
              <li class="nav-item">
                <a class="nav-link" href="#/profile/${user.username}">
                  <img class="user-pic" src="${secureImageSrc(user.image)}">
                  ${user.username}
                </a>
              </li>`
              : /* html */ `
              <li class="nav-item">
                <a class="nav-link" href="#/login">Sign in</a>
              </li>
              <li class="nav-item">
                <a class="nav-link" href="#/register">Sign up</a>
              </li>`
            }
          </ul>
        </div>
      </nav>
    `
  }
}
