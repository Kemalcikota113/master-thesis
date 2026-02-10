// @ts-check

/* global CustomEvent */
/* global HTMLElement */

/**
 * can be used with the two attributes and then ignores user login status by listenToUser and changes labels for profile sites
 * else it will behave normal as a sub-navigation on home with Your feed which only works when logged in
 * https://github.com/Weedshaker/event-driven-web-components-realworld-example-app/blob/master/FRONTEND_INSTRUCTIONS.md#home
 * As a molecule, this component shall hold Atoms
 *
 * @export
 * @attribute {
 *  favorited?: string,
 *  author?: string,
 *  itsMe?: boolean
 * }
 * @class ArticleFeedToggle
 */
export default class ArticleFeedToggle extends HTMLElement {
  constructor () {
    super()

    /** @type {boolean} */
    this.isLoggedIn = false
    /** @type {import("../controllers/Article").RequestListArticlesEventDetail} */
    this.query = {}

    /**
     * Listens to the event name/typeArg: 'listArticles'
     *
     * @param {CustomEvent & {detail: import("../controllers/Article").ListArticlesEventDetail}} event
     */
    this.listArticlesListener = event => {
      this.query = event.detail.query
      this.render()
    }

    /**
     * Listens to the event name/typeArg: 'user'
     *
     * @param {CustomEvent & {detail: import("../controllers/User.js").UserEventDetail}} event
     */
    this.userListener = event => {
      event.detail.fetch.then(user => {
        if (!this.isLoggedIn) {
          this.isLoggedIn = true
          this.render()
        }
      }).catch(error => {
        console.log(`Error@UserFetch: ${error}`)
        if (this.isLoggedIn) {
          this.isLoggedIn = false
          this.render()
        }
      })
    }

    /**
     * target href to dispatch a CustomEvent requestListArticles, which will trigger ListArticlePreviews to render with new query
     *
     * @param {event & {target: HTMLElement}} event
     * @return {void | false}
     */
    this.clickListener = event => {
      if (!event.target) return false
      event.preventDefault()
      if (event.target.id === 'your-feed' && !event.target.classList.contains('disabled')) {
        // get logged in users feed
        this.dispatchEvent(new CustomEvent('requestListArticles', {
          /** @type {import("../controllers/Article.js").RequestListArticlesEventDetail} */
          detail: {
            showYourFeed: this.isLoggedIn,
            author: this.getAttribute('author') || ''
          },
          bubbles: true,
          cancelable: true,
          composed: true
        }))
      } else {
        // on every link click it will attempt to get articles by tags
        this.dispatchEvent(new CustomEvent('requestListArticles', {
          /** @type {import("../controllers/Article.js").RequestListArticlesEventDetail} */
          detail: {
            favorited: this.getAttribute('favorited') || ''
          },
          bubbles: true,
          cancelable: true,
          composed: true
        }))
      }
    }
  }

  connectedCallback () {
    document.body.addEventListener('listArticles', this.listArticlesListener)
    this.addEventListener('click', this.clickListener)
    if (this.shouldComponentRender()) this.render()
    if (this.listenToUser) {
      document.body.addEventListener('user', this.userListener)
      this.dispatchEvent(new CustomEvent('getUser', {
        bubbles: true,
        cancelable: true,
        composed: true
      }))
    }
  }

  disconnectedCallback () {
    document.body.removeEventListener('listArticles', this.listArticlesListener)
    this.removeEventListener('click', this.clickListener)
    if (this.listenToUser) document.body.removeEventListener('user', this.userListener)
  }

  /**
   * evaluates if a render is necessary
   *
   * @return {boolean}
   */
  shouldComponentRender () {
    return !this.innerHTML
  }

  /**
   * renders the header within the body, which is in this case the navbar
   *
   * @return {void}
   */
  render () {
    /**
     * three list elements 0: Your Feed or Users Posts, 1: Global Feed or Users Favorited Posts, 2: Tags
     * @type {0 | 1 | 2}
     */
    const active = this.query.tag ? 2 : this.query.showYourFeed || this.query.author ? 0 : !this.query.showYourFeed || this.query.favorited ? 1 : 0
    /**
     * 0: Your Feed or Users Post disabled?
     * @type {boolean}
     */
    const disabled = this.listenToUser && !this.isLoggedIn
    this.innerHTML = `
      <div class="feed-toggle">
        <ul class="nav nav-pills outline-active">
          <li class="nav-item">
            <a id=your-feed class="nav-link${disabled ? ' disabled' : ''} ${active === 0 ? 'active' : ''}" href="#/">${this.getAttribute('author') ? `${this.getAttribute('itsMe') ? 'My' : this.getAttribute('author')} Posts` : 'Your Feed'}</a>
          </li>
          <li class="nav-item">
            <a class="nav-link ${active === 1 ? 'active' : ''}" href="#/">${this.getAttribute('favorited') ? `${this.getAttribute('itsMe') ? '' : `${this.getAttribute('author')} `}Favorited Posts` : 'Global Feed'}</a>
          </li>
          ${active === 2 ? `
            <li class="nav-item">
              <a href="#/" class="nav-link active">
                <i class="ion-pound"></i> ${this.query.tag}
              </a>
            </li>
          ` : ''}
        </ul>
      </div>
    `
  }

  get listenToUser () {
    return !this.getAttribute('author') && !this.getAttribute('favorited')
  }
}
