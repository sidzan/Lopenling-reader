import {
  CategoryColorLine,
  ReaderNavigationMenuSearchButton,
  ReaderNavigationMenuCloseButton,
  ReaderNavigationMenuDisplaySettingsButton,
  LoadingMessage,
} from './Misc';
import React  from 'react';
import ReactDOM  from 'react-dom';
import $  from './sefaria/sefariaJquery';
import Sefaria  from './sefaria/sefaria';
import classNames  from 'classnames';
import PropTypes  from 'prop-types';
import Footer  from './Footer';
import SearchResultList  from './SearchResultList';
import Component from 'react-class';


class SearchPage extends Component {
    constructor(props) {
      super(props);
      this.state = {};
    }
    render () {
        var fontSize       = 62.5; // this.props.settings.fontSize, to make this respond to user setting. disabled for now.
        var style          = {"fontSize": fontSize + "%"};
        var classes        = classNames({readerNavMenu: 1, noHeader: this.props.hideNavHeader});
        var contentClasses = classNames({content: 1, hasFooter: this.props.panelsOpen === 1});
        var isQueryHebrew  = Sefaria.hebrew.isHebrew(this.props.query);
        return (<div className={classes} key={this.props.query}>
                  {this.props.hideNavHeader ? null :
                    (<div className="readerNavTop search">
                      <CategoryColorLine category="Other" />
                      <div className="readerNavTopStart">
                        <ReaderNavigationMenuCloseButton onClick={this.props.close}/>
                        <SearchBar
                          initialQuery = { this.props.query }
                          updateQuery = { this.props.onQueryChange } />
                      </div>
                    </div>)}
                  <div className={contentClasses}>
                    <div className="contentInner">
                      <div className="searchContentFrame">
                          <h1 className={classNames({"hebrewQuery": isQueryHebrew, "englishQuery": !isQueryHebrew})}>
                            &ldquo;{ this.props.query }&rdquo;
                          </h1>
                          <div className="searchContent" style={style}>
                              <SearchResultList
                                interfaceLang={this.props.interfaceLang}
                                query={this.props.query}
                                tab={this.props.tab}
                                textSearchState={this.props.textSearchState}
                                sheetSearchState={this.props.sheetSearchState}
                                onResultClick={this.props.onResultClick}
                                updateTab={this.props.updateTab}
                                updateAppliedFilter = {this.props.updateAppliedFilter}
                                updateAppliedOptionField={this.props.updateAppliedOptionField}
                                updateAppliedOptionSort={this.props.updateAppliedOptionSort}
                                registerAvailableFilters={this.props.registerAvailableFilters}
                                openProfile={this.props.openProfile}
                              />
                          </div>
                      </div>
                    </div>
                    { this.props.panelsOpen === 1 ? <Footer /> : null }
                  </div>
                </div>);
    }
}
SearchPage.propTypes = {
    interfaceLang:            PropTypes.oneOf(["english", "hebrew"]),
    query:                    PropTypes.string,
    tab:                      PropTypes.oneOf(["text", "sheet"]),
    textSearchState:          PropTypes.object,
    sheetSearchState:         PropTypes.object,
    settings:                 PropTypes.object,
    panelsOpen:               PropTypes.number,
    close:                    PropTypes.func,
    onResultClick:            PropTypes.func,
    onQueryChange:            PropTypes.func,
    updateTab:                PropTypes.func,
    updateAppliedFilter:      PropTypes.func,
    updateAppliedOptionField: PropTypes.func,
    updateAppliedOptionSort:  PropTypes.func,
    registerAvailableFilters: PropTypes.func,
    hideNavHeader:            PropTypes.bool,
    openProfile:              PropTypes.func.isRequired,
};


class SearchBar extends Component {
    constructor(props) {
      super(props);

      this.state = {query: props.initialQuery};
    }
    handleKeypress(event) {
        if (event.charCode == 13) {

            this.updateQuery();
            // Blur search input to close keyboard
            $(ReactDOM.findDOMNode(this)).find(".readerSearch").blur();
        }
    }
    updateQuery() {
        if (this.props.updateQuery) {
            this.props.updateQuery(this.state.query)
        }
    }
    handleChange(event) {
        this.setState({query: event.target.value});
    }
    render () {
        return (
          <div className="searchBox">
              <ReaderNavigationMenuSearchButton onClick={this.updateQuery} />
              <input
                className="readerSearch"
                  id="searchInput"
                  title="Search for Texts or Keywords Here"
                  value={this.state.query}
                  onKeyPress={this.handleKeypress}
                  onChange={this.handleChange}
                  placeholder="Search"/>
          </div>
        )
    }
}
SearchBar.propTypes = {
    initialQuery: PropTypes.string,
    updateQuery: PropTypes.func
};


export default SearchPage;
