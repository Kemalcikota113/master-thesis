// @ts-check

import { Environment } from '../../helpers/Environment.js'
import { secureImageSrc } from '../../helpers/Utils.js'

/* global HTMLElement */
/* global customElements */
/* global CustomEvent */

/**
 * https://github.com/Weedshaker/event-driven-web-components-realworld-example-app/blob/master/FRONTEND_INSTRUCTIONS.md#article
 * As a page, this component becomes a domain dependent container and shall hold organisms, molecules and/or atoms
 *
 * @export
 * @class Article
 */
export default class Article extends HTMLElement {
  constructor () {
    super()

    this.loading = /* html */'<div class="profile-page"><div class="user-info"><div class="container"><div class="row">Loading...</div></div></div></div>'

    this.profileListener = event => {
      event.detail.fetch.then(({ profile }) => { if (this.shouldComponentRender(profile, undefined)) this.render(profile, undefined) }).catch(error => {
        if (this.shouldComponentRender(null, undefined)) this.render(null, undefined)
        console.log(`Error@ProfileFetch: ${error}`)
      })
    }

    this.userListener = event => {
      event.detail.fetch.then(user => { if (this.shouldComponentRender(undefined, user)) this.render(undefined, user) }).catch(error => {
        if (this.shouldComponentRender(undefined, null)) this.render(undefined, null)
        console.log(`Error@UserFetch: ${error}`)
      })
    }

    this.followBtnListener = event => {
      if (!event.target) return false
      event.preventDefault()
      this.dispatchEvent(new CustomEvent('followUser', {
        /** @type {import("../controllers/MetaActions.js").SetFavoriteEventDetail} */
        detail: {
          profile: this.profile
        },
        bubbles: true,
        cancelable: true,
        composed: true
      }))
    }
  }

  connectedCallback () {
    this.user = undefined
    this.profile = undefined

    this.loadChildComponents()
    document.body.addEventListener('profile', this.profileListener)
    document.body.addEventListener('user', this.userListener)

    this.dispatchEvent(new CustomEvent('getProfile', {
      detail: {
        username: Environment.urlEnding
      },
      bubbles: true,
      cancelable: true,
      composed: true
    }))

    this.dispatchEvent(new CustomEvent('getUser', {
      bubbles: true,
      cancelable: true,
      composed: true
    }))
    // show initial loading because there is no connectCallback render execution
    if (!this.innerHTML) this.innerHTML = this.loading
  }

  disconnectedCallback () {
    document.body.removeEventListener('profile', this.profileListener)
    document.body.removeEventListener('user', this.userListener)
    if (this.btnFollow) this.btnFollow.removeEventListener('click', this.followBtnListener)
    // looks nicer when cleared
    this.innerHTML = ''
  }

  /**
   * evaluates if a render is necessary
   *
   * @param {import("../../helpers/Interfaces.js").Profile} [profile = this.profile]
   * @param {import("../../helpers/Interfaces.js").User} [user = this.user]
   * @return {boolean}
   */
  shouldComponentRender (profile = this.profile, user = this.user) {
    return profile !== this.profile || user !== this.user
  }

  /**
   * renders the profile
   *
   * @param {import("../../helpers/Interfaces.js").Profile} [profile = this.profile]
   * @param {import("../../helpers/Interfaces.js").User} [user = this.user]
   * @return {any}
   */
  render (profile = this.profile, user = this.user) {
    if (user !== undefined) this.user = user
    if (profile !== undefined) this.profile = profile
    if (!profile) return (this.innerHTML = profile === null ? '<div class="profile-page"><div class="user-info"><div class="container"><div class="row">An error occurred fetching the profile!</div></div></div></div>' : this.loading)
    this.innerHTML = /* html */`
    <div class="profile-page">

      <div class="user-info">
        <div class="container">
          <div class="row">

            <div class="col-xs-12 col-md-10 offset-md-1">
              <img src="${secureImageSrc(profile.image)}" class="user-img" />
              <h4>${profile.username}</h4>
              <p>
              ${profile.bio || ''}
              </p>

              ${user && profile && user.username === profile.username
                ? `<a class="btn btn-outline-secondary btn-sm action-btn" href="#/settings">
                  <i class="ion-gear-a"></i> Edit Profile Settings
                </a>`
                : `<button name="follow" class="btn btn-sm  action-btn ${profile.following ? 'btn-secondary ' : 'btn-outline-secondary '}">
                  <i class="${profile.following ? 'ion-minus-round' : 'ion-plus-round'}"></i>
                  &nbsp;
                  ${profile.following ? 'Unfollow' : 'Follow'} ${profile.username}
                </button>`
              }
              </div>

          </div>
        </div>
      </div>

      <div class="container">
        <div class="row">

          <div class="col-xs-12 col-md-10 offset-md-1">

            <div class="articles-toggle">
              <m-article-feed-toggle favorited="${profile.username}" author="${profile.username}" itsMe=${user && user.username === profile.username ? 'true' : ''}></m-article-feed-toggle>
            </div>

            <o-list-article-previews><div class="article-preview">Loading...</div></o-list-article-previews>

            <m-pagination author="${profile.username}"></m-pagination>

          </div>

        </div>
      </div>

    </div>
    `
    if (this.btnFollow) this.btnFollow.addEventListener('click', this.followBtnListener)
  }

  /**
   * fetch children when first needed
   *
   * @returns {Promise<[string, CustomElementConstructor][]>}
   */
  loadChildComponents () {
    return this.childComponentsPromise || (this.childComponentsPromise = Promise.all([
      import('../molecules/ArticleFeedToggle.js').then(
        /** @returns {[string, CustomElementConstructor]} */
        module => ['m-article-feed-toggle', module.default]
      ),
      import('../organisms/ListArticlePreviews.js').then(
        /** @returns {[string, CustomElementConstructor]} */
        module => ['o-list-article-previews', module.default]
      ),
      import('../molecules/Pagination.js').then(
        /** @returns {[string, CustomElementConstructor]} */
        module => ['m-pagination', module.default]
      )
    ]).then(elements => {
      elements.forEach(element => {
        // don't define already existing customElements
        // @ts-ignore
        if (!customElements.get(element[0])) customElements.define(...element)
      })
      return elements
    }))
  }

  get btnFollow () {
    return this.querySelector('button[name=follow]')
  }
}
